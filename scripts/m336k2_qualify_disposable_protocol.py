"""Create and verify a disposable M336K2 Q/F/H/E chain.

The route commands are executed by :mod:`m336k2_run_final_route`; in
particular, the H-publication command must commit and push H-like before the
controller permits evaluator reservation, and the E-publication command must
commit and push E-like before final verification.  This coordinator owns the
disposable Git topology and independently verifies it after the controller
returns.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_freeze import materialize_m336k2_f28
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    M336K2ProtocolError,
    attest_committed_f28,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    verify_m336k2_commit_protocol,
)
from ai_brain.stage3.acquisition.m336k2_readiness import (
    M336K2ReadinessEvidence,
    build_m336k2_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "source_repository",
        "git_executable",
        "python_executable",
        "exact_implementation_tip",
        "disposable_branch",
        "output",
        "q_evidence_source",
        "q_relative_root",
        "readiness_evidence",
        "component_sources",
        "freeze_relative_root",
        "publication_contract",
        "route_request_template",
        "stage_request_template",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K2 disposable request fields changed")
    output = Path(request["output"]).resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K2 disposable output must be fresh")
    output.mkdir(parents=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    python = Path(request["python_executable"]).resolve(strict=True)
    source = Path(request["source_repository"]).resolve(strict=True)
    implementation = request["exact_implementation_tip"]
    branch = request["disposable_branch"]
    if not branch.startswith("disposable/m336k2-"):
        raise M336K2ProtocolError("M336K2 disposable branch namespace changed")
    remote = output / "origin.git"
    repository = output / "repository"
    private = output / "private"
    public = output / "public"
    private.mkdir()
    public.mkdir()
    _git(git, None, "init", "--bare", str(remote))
    _git(git, None, "clone", "--no-local", str(source), str(repository))
    _git(git, repository, "config", "user.email", "m336k2@example.invalid")
    _git(git, repository, "config", "user.name", "M336K2 Disposable Proof")
    _git(git, repository, "remote", "set-url", "origin", str(remote))
    _git(git, repository, "checkout", "--detach", implementation)
    _git(git, repository, "checkout", "-B", branch, implementation)
    _require_clean_head(git, repository, implementation)
    _git(git, repository, "push", "-u", "origin", branch)

    runtime = private / "runtime"
    destinations = {
        "acquisition_ledger": runtime / "ledgers" / "acquisition.jsonl",
        "selector_ledger": runtime / "ledgers" / "selector.jsonl",
        "evaluator_ledger": runtime / "ledgers" / "evaluator.jsonl",
        "route_state_ledger": runtime / "ledgers" / "route.jsonl",
        "vault": runtime / "vault",
        "selected_source_snapshot": runtime / "windows-selected",
        "windows_production": runtime / "windows-production",
        "karina_production": runtime / "karina-production",
        "evaluator_root": runtime / "evaluator",
    }
    evidence = tuple(
        M336K2ReadinessEvidence(
            name=name,
            path=Path(spec["path"]),
            hash_field=spec["hash_field"],
            expected_status=spec["expected_status"],
        )
        for name, spec in sorted(request["readiness_evidence"].items())
    )
    readiness = build_m336k2_readiness(
        repository=repository,
        git_executable=git,
        exact_implementation_tip=implementation,
        evidence=evidence,
        final_destinations=destinations,
        expected_branch=branch,
    )
    readiness_path = private / "disposable_readiness.json"
    readiness_path.write_text(
        canonical_json(asdict(readiness)) + "\n", encoding="utf-8", newline="\n"
    )

    contract_path = Path(request["publication_contract"]).resolve(strict=True)
    contract = publication_contract_from_dict(_object(contract_path))
    if contract.branch_ref != f"refs/heads/{branch}":
        raise M336K2ProtocolError("M336K2 disposable publication branch changed")
    q_relative = request["q_relative_root"]
    if q_relative != contract.q_root:
        raise M336K2ProtocolError("M336K2 disposable Q root changed")
    q_destination = _safe_repository_destination(repository, q_relative)
    shutil.copytree(
        Path(request["q_evidence_source"]).resolve(strict=True), q_destination
    )
    if (q_destination / "readiness.json").exists():
        raise M336K2ProtocolError("M336K2 disposable readiness is duplicated")
    shutil.copyfile(readiness_path, q_destination / "readiness.json")
    q_manifest_path = q_destination / "evidence_manifest.json"
    _write_q_manifest(q_destination, q_manifest_path)
    _reject_source_tree(q_destination)
    q28 = _commit(git, repository, contract.q_subject)
    _git(git, repository, "push", "-u", "origin", branch)
    if _git(git, repository, "rev-parse", f"{q28}^") != implementation:
        raise M336K2ProtocolError("M336K2 disposable Q-like parent changed")

    replacements = {
        "@IMPLEMENTATION_TIP@": implementation,
        "@Q_SHA@": q28,
        "@BRANCH_REF@": contract.branch_ref,
        "@READINESS_HASH@": readiness.readiness_hash,
    }
    components = {}
    rendered_components = private / "components"
    rendered_components.mkdir()
    for name, raw_path in sorted(request["component_sources"].items()):
        source_path = (
            readiness_path
            if name == "q28_readiness"
            else q_manifest_path
            if name == "q28_evidence_manifest"
            else Path(raw_path).resolve(strict=True)
        )
        value = _rehash_top_level(_replace(_object(source_path), replacements))
        target = rendered_components / f"{name}.json"
        target.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
        components[name] = target
    freeze_relative = request["freeze_relative_root"]
    if freeze_relative != contract.f_root:
        raise M336K2ProtocolError("M336K2 disposable F root changed")
    freeze_root = _safe_repository_destination(repository, freeze_relative)
    build = materialize_m336k2_f28(
        repository=repository,
        git_executable=git,
        exact_implementation_tip=implementation,
        exact_q28_sha=q28,
        readiness=readiness_path,
        component_sources=components,
        output=freeze_root,
        expected_branch=branch,
        freeze_relative_root=freeze_relative,
    )
    f28 = _commit(git, repository, contract.f_subject)
    _git(git, repository, "push", "origin", branch)
    freeze = _freeze(freeze_root / "freeze_manifest.json")
    attestation = attest_committed_f28(
        repository,
        git,
        freeze_manifest=freeze,
        exact_f28_sha=f28,
    )
    attestation_path = private / "f28_attestation.json"
    attestation_path.write_text(
        canonical_json(asdict(attestation)) + "\n", encoding="utf-8", newline="\n"
    )

    route_template = _object(
        Path(request["route_request_template"]).resolve(strict=True)
    )
    stage_template = _object(
        Path(request["stage_request_template"]).resolve(strict=True)
    )
    route_replacements = {
        **replacements,
        "@F_SHA@": f28,
        "@REPOSITORY@": str(repository),
        "@GIT_EXECUTABLE@": str(git),
        "@FREEZE_MANIFEST@": str(freeze_root / "freeze_manifest.json"),
        "@F28_ATTESTATION@": str(attestation_path),
        "@PRIVATE_ROOT@": str(runtime),
        "@STAGE_STATE@": str(runtime / "stage-state.json"),
        "@STAGE_RECEIPT_ROOT@": str(runtime / "stage-receipts"),
        "@ACQUISITION_LEDGER@": str(destinations["acquisition_ledger"]),
        "@SELECTOR_LEDGER@": str(destinations["selector_ledger"]),
        "@EVALUATOR_LEDGER@": str(destinations["evaluator_ledger"]),
        "@ROUTE_LEDGER@": str(destinations["route_state_ledger"]),
        "@ROUTE_RECEIPT@": str(runtime / "route-receipt.json"),
        "@VAULT@": str(destinations["vault"]),
        "@SELECTED_SOURCE_SNAPSHOT@": str(destinations["selected_source_snapshot"]),
        "@WINDOWS_PRODUCTION@": str(destinations["windows_production"]),
        "@KARINA_PRODUCTION@": str(destinations["karina_production"]),
        "@EVALUATOR_ROOT@": str(destinations["evaluator_root"]),
        "@PUBLICATION_CONTRACT@": str(contract_path),
    }
    for component in freeze.components:
        route_replacements[f"@COMPONENT_{component.name.upper()}@"] = str(
            repository.joinpath(*component.relative_path.split("/"))
        )
    stage_request = _replace(stage_template, route_replacements)
    stage_request_path = private / "stage_request.json"
    stage_request_path.write_text(
        canonical_json(stage_request) + "\n", encoding="utf-8", newline="\n"
    )
    route_replacements["@STAGE_REQUEST@"] = str(stage_request_path)
    route_request = _replace(route_template, route_replacements)
    route_request_path = private / "route_request.json"
    route_request_path.write_text(
        canonical_json(route_request) + "\n", encoding="utf-8", newline="\n"
    )
    environment = m336k2_minimal_environment()
    environment["PYTHONPATH"] = str(repository / "src")
    result = subprocess.run(
        (
            str(python),
            "-B",
            str(repository / "scripts" / "m336k2_run_final_route.py"),
            "--request",
            str(route_request_path),
        ),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
    )
    if result.returncode:
        raise M336K2ProtocolError("M336K2 disposable typed controller failed")
    route_receipt = _object((runtime / "route-receipt.json").resolve(strict=True))
    e28 = _git(git, repository, "rev-parse", "HEAD^{commit}")
    h28 = _git(git, repository, "rev-parse", f"{e28}^")
    protocol = verify_m336k2_commit_protocol(
        repository=repository,
        git_executable=git,
        exact_q28_sha=q28,
        exact_f28_sha=f28,
        exact_h28_sha=h28,
        exact_e28_sha=e28,
        contract=contract,
    )
    ordered = tuple(
        _git(
            git,
            repository,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{implementation}..{e28}",
        ).splitlines()
    )
    if ordered != (q28, f28, h28, e28):
        raise M336K2ProtocolError("M336K2 disposable chain is not exactly Q/F/H/E")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_DISPOSABLE_FULL_CHAIN_PROOF",
        "implementation_tip": implementation,
        "q_like_sha": q28,
        "f_like_sha": f28,
        "h_like_sha": h28,
        "e_like_sha": e28,
        "ordered_commit_shas": ordered,
        "freeze_build_receipt_hash": build.receipt_hash,
        "f_attestation_hash": attestation.attestation_hash,
        "route_receipt_hash": route_receipt["receipt_hash"],
        "commit_protocol_receipt_hash": protocol["receipt_hash"],
        "source_leak_count": protocol["source_leak_count"],
        "absolute_path_count": protocol["absolute_path_count"],
        "private_public_artifact_count": protocol["private_artifact_count"],
        "post_f_implementation_change_count": protocol[
            "post_f28_implementation_change_count"
        ],
        "final_real_one_shot_counter_count": 0,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    receipt_path = public / "disposable_protocol_receipt.json"
    receipt_path.write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(receipt))


def _git(git: Path, repository: Path | None, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()


def _commit(git: Path, repository: Path, subject: str) -> str:
    _git(git, repository, "add", "-A")
    _git(git, repository, "commit", "-m", subject)
    return _git(git, repository, "rev-parse", "HEAD^{commit}")


def _require_clean_head(git: Path, repository: Path, expected: str) -> None:
    if _git(git, repository, "rev-parse", "HEAD^{commit}") != expected or _git(
        git, repository, "status", "--porcelain=v1"
    ):
        raise M336K2ProtocolError("M336K2 disposable source is not clean/exact")


def _safe_repository_destination(repository: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or not relative.startswith("artifacts/m336k2/disposable/")
    ):
        raise M336K2ProtocolError("M336K2 disposable artifact root is unsafe")
    return repository.joinpath(*path.parts)


def _reject_source_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if (
            path.suffix.casefold()
            in {".java", ".class", ".jar", ".zip", ".tar", ".gz", ".tgz"}
            or b"public class " in raw
            or b"package " in raw
        ):
            raise M336K2ProtocolError("M336K2 disposable Q contains source material")


def _write_q_manifest(root: Path, output: Path) -> None:
    rows = tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file() and item != output),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_Q28_EVIDENCE_MANIFEST",
        "files": rows,
        "file_count": len(rows),
        "tree_hash": content_hash(rows),
        "source_leak_count": 0,
        "absolute_path_count": 0,
        "private_artifact_count": 0,
        "status": "PASS",
    }
    output.write_text(
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _replace(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def _rehash_top_level(value: dict) -> dict:
    primary = tuple(
        name
        for name in (
            "authorization_hash",
            "receipt_hash",
            "manifest_hash",
            "registry_hash",
            "policy_hash",
            "contract_hash",
            "threshold_manifest_hash",
            "frozen_file_manifest_hash",
        )
        if name in value
    )
    if len(primary) > 1:
        raise M336K2ProtocolError("M336K2 disposable component hash is ambiguous")
    if primary:
        body = dict(value)
        field = primary[0]
        body.pop(field)
        return {**body, field: content_hash(body)}
    return value


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 disposable input is invalid JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 disposable input must be an object")
    return value


def _freeze(path: Path) -> M336K2FreezeManifest:
    value = _object(path)
    value["components"] = tuple(
        M336K2FrozenComponent(**item) for item in value["components"]
    )
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    return M336K2FreezeManifest(**value)


if __name__ == "__main__":
    main()

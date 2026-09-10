"""Typed prospective F28 materialization for M-33.6k.2."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_BRANCH,
    M336K2_READY_STATUS,
    M336K2_REQUIRED_FREEZE_COMPONENTS,
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    M336K2ProtocolError,
    m336k2_minimal_environment,
    verify_complete_freeze,
)
from ai_brain.stage3.acquisition.m336k2_readiness import readiness_from_dict

M336K2_F28_ROOT = Path("artifacts/m336k2/f28-freeze")
M336K2_F28_SELF_REFERENCE_EXCLUSIONS = (
    (M336K2_F28_ROOT / "freeze_manifest.json").as_posix(),
    (M336K2_F28_ROOT / "f28_build_receipt.json").as_posix(),
)


@dataclass(frozen=True)
class M336K2F28BuildResult:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    exact_q28_sha: str
    freeze_root: str
    component_count: int
    frozen_file_count: int
    prospective_freeze_tree_hash: str
    freeze_manifest_hash: str
    status: str
    receipt_hash: str


def materialize_m336k2_f28(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    exact_q28_sha: str,
    readiness: Path,
    component_sources: dict[str, Path],
    output: Path,
    expected_branch: str = M336K2_BRANCH,
    freeze_relative_root: str = M336K2_F28_ROOT.as_posix(),
) -> M336K2F28BuildResult:
    """Create metadata-only prospective F28 material without spending final state."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    destination = output.resolve(strict=False)
    relative_output = destination.relative_to(root).as_posix()
    if (
        destination.exists()
        or set(component_sources) != M336K2_REQUIRED_FREEZE_COMPONENTS
        or relative_output != freeze_relative_root
        or not _safe_artifact_root(freeze_relative_root)
    ):
        raise M336K2ProtocolError("M336K2 F28 destination/component set changed")
    _verify_q_lineage(
        root,
        git,
        exact_implementation_tip=exact_implementation_tip,
        exact_q28_sha=exact_q28_sha,
        expected_branch=expected_branch,
    )
    readiness_value = readiness_from_dict(_object(readiness.resolve(strict=True)))
    if (
        readiness_value.exact_implementation_tip != exact_implementation_tip
        or readiness_value.branch != expected_branch
        or readiness_value.upstream_sha != exact_implementation_tip
        or readiness_value.remote_sha != exact_implementation_tip
        or readiness_value.status != M336K2_READY_STATUS
        or any(
            (
                readiness_value.acquisition_reservations,
                readiness_value.acquisition_invocations,
                readiness_value.selector_reservations,
                readiness_value.selector_invocations,
                readiness_value.evaluator_reservations,
                readiness_value.evaluator_invocations,
                readiness_value.route_state_events,
                readiness_value.final_candidate_source_body_bytes,
            )
        )
    ):
        raise M336K2ProtocolError("M336K2 F28 readiness is not sealed and unspent")
    destination.mkdir(parents=True)
    components = []
    try:
        component_root = destination / "components"
        component_root.mkdir()
        for index, name in enumerate(sorted(component_sources)):
            source = component_sources[name].resolve(strict=True)
            if source.suffix.casefold() not in {".json", ".jsonl"}:
                raise M336K2ProtocolError("M336K2 F28 component is not metadata")
            _reject_source_body(source)
            target = component_root / f"{index:02d}-{name}.json"
            shutil.copyfile(source, target)
            relative = target.relative_to(root).as_posix()
            components.append(
                M336K2FrozenComponent(
                    name=name,
                    relative_path=relative,
                    bytes_hash=bytes_hash(target.read_bytes()),
                    byte_count=target.stat().st_size,
                )
            )
        frozen_rows = tuple(
            (
                item.relative_path,
                item.byte_count,
                item.bytes_hash,
            )
            for item in components
        )
        frozen_body = {
            "schema_version": 1,
            "contract_role": "M336K2_F28_FROZEN_FILE_MANIFEST",
            "files": frozen_rows,
            "file_count": len(frozen_rows),
        }
        frozen_value = {
            **frozen_body,
            "frozen_file_manifest_hash": content_hash(frozen_body),
        }
        (destination / "frozen_file_manifest.json").write_text(
            canonical_json(frozen_value) + "\n", encoding="utf-8", newline="\n"
        )
        prospective_rows = _tree_rows(destination)
        prospective = content_hash(prospective_rows)
        authorization_hash = _semantic_component_hash(
            component_sources["final_authorization"], "authorization_hash"
        )
        route_hash = _semantic_component_hash(
            component_sources["route_manifest"], "manifest_hash"
        )
        manifest_body = {
            "schema_version": 1,
            "contract_role": "M336K2_F28_FREEZE",
            "implementation_tip": exact_implementation_tip,
            "exact_q28_sha": exact_q28_sha,
            "exact_f28_sha": "0" * 40,
            "committed_f28_tree": "0" * 40,
            "readiness_hash": readiness_value.readiness_hash,
            "authorization_hash": authorization_hash,
            "route_hash": route_hash,
            "components": tuple(components),
            "self_reference_safe_exclusions": (
                f"{relative_output}/freeze_manifest.json",
                f"{relative_output}/f28_build_receipt.json",
            ),
            "prospective_freeze_tree_hash": prospective,
        }
        manifest = M336K2FreezeManifest(
            **manifest_body, manifest_hash=content_hash(manifest_body)
        )
        manifest_path = destination / "freeze_manifest.json"
        manifest_path.write_text(
            canonical_json(asdict(manifest)) + "\n", encoding="utf-8", newline="\n"
        )
        verify_complete_freeze(root, manifest, allow_prospective_f28=True)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_F28_BUILD_RECEIPT",
        "exact_implementation_tip": exact_implementation_tip,
        "exact_q28_sha": exact_q28_sha,
        "freeze_root": relative_output,
        "component_count": len(components),
        "frozen_file_count": len(_tree_rows(destination)),
        "prospective_freeze_tree_hash": prospective,
        "freeze_manifest_hash": manifest.manifest_hash,
        "status": "PASS",
    }
    receipt = M336K2F28BuildResult(**body, receipt_hash=content_hash(body))
    (destination / "f28_build_receipt.json").write_text(
        canonical_json(asdict(receipt)) + "\n", encoding="utf-8", newline="\n"
    )
    return receipt


def _verify_q_lineage(
    root: Path,
    git: Path,
    *,
    exact_implementation_tip: str,
    exact_q28_sha: str,
    expected_branch: str,
) -> None:
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    parent = _git(git, root, "rev-parse", "HEAD^1")
    branch = _git(git, root, "branch", "--show-current")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote_rows = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()
    remote = remote_rows[0] if remote_rows else ""
    dirty = _git(git, root, "status", "--porcelain=v1")
    implementation_changes = _git(
        git,
        root,
        "diff",
        "--name-only",
        exact_implementation_tip,
        exact_q28_sha,
        "--",
        "src",
        "scripts",
        "tools",
        "tests",
        "schemas",
    )
    if (
        head != exact_q28_sha
        or parent != exact_implementation_tip
        or branch != expected_branch
        or upstream != head
        or remote != head
        or dirty
        or implementation_changes
    ):
        raise M336K2ProtocolError("M336K2 F28 requires exact pushed evidence-only Q28")


def _reject_source_body(path: Path) -> None:
    raw = path.read_bytes()
    lowered = path.name.casefold()
    if (
        len(raw) > 20_000_000
        or lowered.endswith((".java", ".jar", ".zip", ".tar", ".gz", ".tgz"))
        or b"public class " in raw
        or b"package " in raw
    ):
        raise M336K2ProtocolError("M336K2 F28 component contains source material")
    try:
        json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 F28 component is not strict JSON") from error


def _semantic_component_hash(path: Path, field: str) -> str:
    value = _object(path.resolve(strict=True))
    claimed = value.get(field)
    body = dict(value)
    body.pop(field, None)
    if (
        not isinstance(claimed, str)
        or len(claimed) != 64
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 F28 semantic component hash changed")
    return claimed


def _tree_rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _safe_artifact_root(value: str) -> bool:
    path = Path(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and value not in {"", "."}
        and ".." not in path.parts
        and "\\" not in value
        and path.parts[0] == "artifacts"
    )


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 F28 input is invalid JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 F28 input is not an object")
    return value


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()

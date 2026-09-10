"""Build and acquire the private, generated M-33.6i provider rehearsal corpus."""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336I_FINAL_ACQUISITION_RUN_ID,
    M336I_FREEZE_MANIFEST_PATH,
    M336I_FROZEN_AUTHORIZATION_PATH,
    M336IFinalAcquisitionLedger,
    M336IFinalAcquisitionRequest,
    acquisition_provider_identity,
    build_m336i_final_acquisition_authorization,
    compute_m336i_commit_tree_identity,
    compute_m336i_freeze_tree_identity,
    run_m336i_frozen_final_acquisition,
)
from ai_brain.stage3.acquisition.m336i_registry import (
    build_m336i_final_java_route_manifest,
    build_m336i_final_java_route_registry,
)
from ai_brain.stage3.acquisition.spdx_license import SPDX_SNAPSHOT_ROOT

FAMILIES = ("fixture-alpha", "fixture-beta", "fixture-gamma")
FILES_PER_FAMILY = 60
METHODS_PER_CLASS = 5
FIXTURE_COMMIT = "1" * 40


def _run(*command: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _zip_bytes(entries: tuple[tuple[str, bytes], ...]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


def _java_entries(family: str) -> tuple[tuple[str, bytes], ...]:
    package = family.replace("-", "_")
    entries = []
    for index in range(FILES_PER_FAMILY):
        methods = "".join(
            f"  public int value{index:03d}_{ordinal}(int input) "
            f"{{ return input + {index + ordinal}; }}\n"
            for ordinal in range(METHODS_PER_CLASS)
        )
        entries.append(
            (
                f"com/example/{package}/C{index:03d}.java",
                (
                    f"package com.example.{package};\n"
                    f"public final class C{index:03d} {{\n"
                    f"  public C{index:03d}() {{}}\n"
                    f"{methods}"
                    "}\n"
                ).encode(),
            )
        )
    return tuple(entries)


def _source_archive(family: str) -> bytes:
    license_raw = (SPDX_SNAPSHOT_ROOT / "Apache-2.0.txt").read_bytes()
    return _zip_bytes((*_java_entries(family), ("LICENSE", license_raw)))


def _scm_archive(family: str) -> bytes:
    license_raw = (SPDX_SNAPSHOT_ROOT / "Apache-2.0.txt").read_bytes()
    root = f"{family}-{FIXTURE_COMMIT}"
    entries = tuple((f"{root}/src/{path}", raw) for path, raw in _java_entries(family))
    return _zip_bytes((*entries, (f"{root}/LICENSE", license_raw)))


def _pom(family: str) -> bytes:
    return (
        "<project><modelVersion>4.0.0</modelVersion>"
        f"<groupId>invalid.m336i</groupId><artifactId>{family}</artifactId>"
        "<version>1.0.0</version></project>\n"
    ).encode()


def _policy(family: str) -> dict:
    source = _source_archive(family)
    body = {
        "family_id": family,
        "organization_id": family,
        "group_id": "invalid.m336i",
        "artifact_id": family,
        "version": "1.0.0",
        "coordinate": f"invalid.m336i:{family}:1.0.0",
        "source_url": f"https://fixture.invalid/{family}-sources.jar",
        "pom_url": f"https://fixture.invalid/{family}.pom",
        "scm_archive_head_url": f"https://fixture.invalid/{family}.zip",
        "source_content_length": len(source),
        "source_sha256_sidecar_available": False,
        "source_sha256_sidecar_value": None,
        "source_signature_available": False,
        "metadata_pom_sha256": bytes_hash(_pom(family)),
        "metadata_receipt_hashes": [content_hash((family, "metadata"))],
        "pom_license_declarations": [
            ["Apache-2.0", "Apache License, Version 2.0", content_hash("Apache-2.0")]
        ],
        "scm_repository": f"https://fixture.invalid/{family}.git",
        "scm_ref": "refs/tags/1.0.0",
        "scm_commit": FIXTURE_COMMIT,
        "repository_source_prefixes": ["src"],
        "metadata_compilation_risk": "ZERO_EXTERNAL_COMPILE_DEPENDENCIES",
        "requirement": "OPTIONAL",
    }
    return {**body, "policy_hash": content_hash(body)}


def _pool() -> dict:
    candidates = [_policy(family) for family in FAMILIES]
    body = {
        "schema_version": 3,
        "policy_version": "m336g.metadata-pool.v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "organization_count": len(candidates),
        "maximum_candidates_per_organization": 1,
        "metadata_compilation_risk_counts": [
            ["ZERO_EXTERNAL_COMPILE_DEPENDENCIES", len(candidates)]
        ],
        "required_candidate_count": 0,
        "optional_candidate_count": len(candidates),
        "pre_f22_source_body_bytes_received": 0,
        "claims_final_eligibility": False,
    }
    return {**body, "pool_hash": content_hash(body)}


class _FixtureMaven:
    def fetch_sources(self, coordinate):
        raw = _source_archive(coordinate.name)
        digest = SimpleNamespace(
            downloaded_bytes_sha256=bytes_hash(raw),
            sidecar_verified=False,
            detached_signature_url=None,
        )
        repository = SimpleNamespace(
            network_receipt_hash=content_hash(
                (
                    "M336I_FIXTURE_SOURCE",
                    coordinate.namespace,
                    coordinate.name,
                    coordinate.version,
                    bytes_hash(raw),
                )
            )
        )
        return SimpleNamespace(payload=raw, digest=digest, repository=repository)

    def fetch_pom(self, coordinate):
        raw = _pom(coordinate.name)
        repository = SimpleNamespace(
            network_receipt_hash=content_hash(
                (
                    "M336I_FIXTURE_POM",
                    coordinate.namespace,
                    coordinate.name,
                    coordinate.version,
                    bytes_hash(raw),
                )
            )
        )
        return SimpleNamespace(payload=raw, repository=repository)


class _FixtureScm:
    def verify(self, *, repository_url: str, requested_ref: str):
        del requested_ref
        family = repository_url.rsplit("/", 1)[-1].removesuffix(".git")
        raw = _scm_archive(family)
        return SimpleNamespace(
            receipt=SimpleNamespace(
                immutable_commit=FIXTURE_COMMIT,
                source_tree_hash=content_hash(
                    tuple(
                        (path, bytes_hash(value))
                        for path, value in _java_entries(family)
                    )
                ),
                receipt_hash=content_hash(
                    ("M336I_FIXTURE_SCM", family, FIXTURE_COMMIT, bytes_hash(raw))
                ),
            ),
            java_entries=tuple(
                (f"src/{path}", value) for path, value in _java_entries(family)
            ),
            license_entries=(
                ("LICENSE", (SPDX_SNAPSHOT_ROOT / "Apache-2.0.txt").read_bytes()),
            ),
            archive_payload=raw,
        )


def _acquire_fixture(policy, *, vault_root: Path, maven, scm):
    from ai_brain.stage3.acquisition.m336d_final_pipeline import _acquire_one

    return _acquire_one(policy, vault_root=vault_root, maven=maven, scm=scm)


def _hashed(path: Path, hash_field: str, **body) -> dict:
    value = {**body, hash_field: content_hash(body)}
    write_canonical_json(path, value)
    return value


def _commit(repository: Path, message: str) -> str:
    _run("git", "add", "-A", cwd=repository)
    _run("git", "commit", "-m", message, cwd=repository)
    return _run("git", "rev-parse", "HEAD", cwd=repository)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authority-statement", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve(strict=False)
    if root.exists():
        raise FileExistsError("M336I authorized rehearsal output must be fresh")
    root.mkdir(parents=True)
    repository = root / "repository"
    remote = root / "remote.git"
    runtime = root / "runtime"
    frozen = repository / "frozen"
    repository.mkdir()
    runtime.mkdir()
    _run("git", "init", "--bare", str(remote))
    _run("git", "init", "-b", "exp/m336i-authorized-rehearsal", str(repository))
    _run("git", "config", "user.email", "m336i@example.invalid", cwd=repository)
    _run("git", "config", "user.name", "M336I Rehearsal", cwd=repository)
    _run("git", "remote", "add", "origin", str(remote), cwd=repository)
    (repository / "base.txt").write_text(
        "Q23 fixture\n", encoding="utf-8", newline="\n"
    )
    q23 = _commit(repository, "Q23 fixture")
    (repository / "r24.txt").write_text("R24 fixture\n", encoding="utf-8", newline="\n")
    r24 = _commit(repository, "R24 fixture")
    frozen.mkdir()
    pool = _pool()
    write_canonical_json(frozen / "candidate_pool.json", pool)
    registry = build_m336i_final_java_route_registry()
    route = build_m336i_final_java_route_manifest(registry)
    write_canonical_json(frozen / "route_registry.json", registry)
    write_canonical_json(frozen / "route_manifest.json", route)
    policy = _hashed(
        frozen / "acquisition_policy.json",
        "acquisition_policy_hash",
        schema_version=1,
        acquisition_run_id=M336I_FINAL_ACQUISITION_RUN_ID,
        acquire_every_frozen_candidate=True,
        replacement_candidates_allowed=False,
        adaptive_family_substitution_allowed=False,
        global_acquisition_count=1,
        windows_acquisition_count=1,
        karina_acquisition_count=0,
        acquisition_reruns_allowed=False,
        allowed_network_hosts=["fixture.invalid"],
    )
    denylist = _hashed(
        frozen / "denylist.json", "denylist_hash", schema_version=1, entries=[]
    )
    authority = _hashed(
        frozen / "authority_root.json",
        "authority_root_hash",
        schema_version=1,
        authority_statement_sha256=bytes_hash(args.authority_statement.read_bytes()),
    )
    shutil.copyfile(args.authority_statement, frozen / "authority.txt")
    selector = _hashed(
        frozen / "selector_policy.json",
        "selector_policy_hash",
        schema_version=1,
        selector="m336f.compilation-closure-selector.v1",
    )
    threshold = _hashed(
        frozen / "threshold.json",
        "threshold_manifest_hash",
        schema_version=1,
        minimum_metrics={},
    )
    publication = _hashed(
        frozen / "publication.json",
        "publication_boundary_policy_hash",
        schema_version=1,
        raw_source_publication=False,
    )
    public_contract = _hashed(
        frozen / "public_contract.json",
        "public_artifact_contract_hash",
        schema_version=1,
        source_bearing_entries=0,
    )
    windows_jdk = "a" * 64
    karina_jdk = "b" * 64
    _hashed(
        frozen / "jdk.json",
        "compiler_jdk_identities_hash",
        schema_version=1,
        windows_public_jdk_receipt_hash=windows_jdk,
        karina_public_jdk_receipt_hash=karina_jdk,
    )
    karina_host = _hashed(
        frozen / "karina_host.json",
        "receipt_hash",
        schema_version=1,
        verification_status="PASS",
        public_jdk_identity_receipt_hash=karina_jdk,
    )
    q24 = _commit(repository, "Q24 fixture")
    freeze_identity = compute_m336i_freeze_tree_identity(repository)
    provider_source, provider_signature = acquisition_provider_identity()
    authorization = build_m336i_final_acquisition_authorization(
        acquisition_mode="REHEARSAL",
        exact_q23_sha=q23,
        r24_implementation_tree_identity=compute_m336i_commit_tree_identity(
            repository, r24
        ),
        q24_evidence_identity="d" * 64,
        f24_parent_sha=q24,
        f24_freeze_tree_identity=freeze_identity,
        route_registry_hash=registry.registry_hash,
        route_manifest_hash=route.manifest_hash,
        acquisition_provider_source_hash=provider_source,
        acquisition_provider_callable_signature_hash=provider_signature,
        candidate_pool_hash=pool["pool_hash"],
        acquisition_policy_hash=policy["acquisition_policy_hash"],
        denylist_hash=denylist["denylist_hash"],
        authority_root_hash=authority["authority_root_hash"],
        selector_policy_hash=selector["selector_policy_hash"],
        threshold_manifest_hash=threshold["threshold_manifest_hash"],
        publication_boundary_hash=publication["publication_boundary_policy_hash"],
        public_artifact_contract_hash=public_contract["public_artifact_contract_hash"],
        windows_public_jdk_identity_receipt_hash=windows_jdk,
        karina_public_jdk_identity_receipt_hash=karina_jdk,
        karina_stable_host_identity_receipt_hash=karina_host["receipt_hash"],
        acquisition_run_id=M336I_FINAL_ACQUISITION_RUN_ID,
        allowed_network_hosts=("fixture.invalid",),
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        branch_ref="refs/heads/exp/m336i-authorized-rehearsal",
    )
    write_canonical_json(repository / M336I_FROZEN_AUTHORIZATION_PATH, authorization)
    freeze_body = {
        "schema_version": 1,
        "authorization_hash": authorization.authorization_hash,
        "f24_parent_sha": q24,
        "f24_freeze_tree_identity": freeze_identity,
        "q24_evidence_identity": authorization.q24_evidence_identity,
        "r24_implementation_tree_identity": (
            authorization.r24_implementation_tree_identity
        ),
    }
    write_canonical_json(
        repository / M336I_FREEZE_MANIFEST_PATH,
        {**freeze_body, "manifest_hash": content_hash(freeze_body)},
    )
    f24 = _commit(repository, "F24 fixture")
    _run(
        "git", "push", "-u", "origin", "exp/m336i-authorized-rehearsal", cwd=repository
    )
    request = M336IFinalAcquisitionRequest(
        repository=repository,
        supplied_f24_sha=f24,
        authorization=authorization,
        candidate_pool=frozen / "candidate_pool.json",
        acquisition_policy=frozen / "acquisition_policy.json",
        denylist=frozen / "denylist.json",
        authority_root=frozen / "authority_root.json",
        authority_statement=frozen / "authority.txt",
        frozen_route_registry=frozen / "route_registry.json",
        frozen_route_manifest=frozen / "route_manifest.json",
        selector_policy=frozen / "selector_policy.json",
        threshold_manifest=frozen / "threshold.json",
        publication_boundary_contract=frozen / "publication.json",
        public_artifact_contract=frozen / "public_contract.json",
        compiler_jdk_identities=frozen / "jdk.json",
        karina_host_identity_receipt=frozen / "karina_host.json",
        acquisition_ledger=runtime / "rehearsal-acquisition.jsonl",
        vault_destination=runtime / "vault",
        private_acquisition_output=runtime / "acquisition-private",
        public_receipt_output=runtime / "public-acquisition-receipt.json",
        public_staging_root=runtime / "public-staging-reserved",
        unused_selected_source_output=runtime / "unused-m336e-selection",
        platform_role="WINDOWS",
    )
    receipt = run_m336i_frozen_final_acquisition(
        request,
        maven_provider=_FixtureMaven(),
        scm_provider=_FixtureScm(),
        acquire_one=_acquire_fixture,
    )
    ledger = M336IFinalAcquisitionLedger(request.acquisition_ledger).receipt()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_AUTHORIZED_ACQUISITION_REHEARSAL",
        "provider_receipt_hash": receipt.receipt_hash,
        "provider_source_hash": provider_source,
        "provider_signature_hash": provider_signature,
        "candidate_count": receipt.acquired_candidate_count,
        "java_file_count": receipt.java_file_count,
        "portable_vault_tree_hash": receipt.portable_vault_tree_hash,
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "rehearsal_acquisition_reservation_count": ledger.acquisition_reservation_count,
        "rehearsal_acquisition_invocation_count": ledger.acquisition_start_count,
        "rehearsal_acquisition_rerun_count": ledger.acquisition_rerun_count,
        "status": "PASS",
    }
    write_canonical_json(
        root / "authorized_acquisition_rehearsal_receipt.json",
        {**body, "receipt_hash": content_hash(body)},
    )
    print(root)


if __name__ == "__main__":
    main()

"""Source-free H26 and evidence-only E26 publication contracts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import (
    M336J3_E26_SUBJECT,
    M336J3_H26_SUBJECT,
    load_m336j_final_freeze_manifest_v2,
)

M336J3_H26_OUTPUT = Path("artifacts/m336j3/h26-production")
M336J3_E26_OUTPUT = Path("artifacts/m336j3/e26-evidence")
_H26_ROOT_FILES = frozenset(
    {
        "m336i_production_seal.json",
        "production_output.json",
        "field_evidence_manifest.json",
        "sealed_source_replay_receipt.json",
        "public_staging_manifest.json",
        "public_staging_receipt.json",
    }
)


def stage_m336j_h26_publication(
    *,
    repository: Path,
    git_executable: Path,
    exact_f26_sha: str,
    freeze_manifest: Path,
    production_source: Path,
    output: Path,
) -> dict:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    manifest = load_m336j_final_freeze_manifest_v2(freeze_manifest)
    _verify_clean_pushed_head(root, git, exact_f26_sha)
    destination = output.resolve(strict=False)
    expected = (root / M336J3_H26_OUTPUT).resolve(strict=False)
    source = production_source.resolve(strict=True)
    if destination != expected or destination.exists() or source.is_relative_to(root):
        raise ValueError("M336J H26 publication paths are invalid")
    candidate_pack = source / "candidate_pack"
    pack = verify_java_public_candidate_pack(candidate_pack)
    destination.mkdir(parents=True)
    shutil.copytree(candidate_pack, destination / "candidate_pack")
    for name in sorted(_H26_ROOT_FILES):
        candidate = source / name
        if candidate.is_file():
            shutil.copyfile(candidate, destination / name)
    _reject_private_payload(destination)
    _reject_public_json_payload(destination, reject_e26_identity=False)
    copied_pack = verify_java_public_candidate_pack(destination / "candidate_pack")
    if copied_pack != pack:
        raise ValueError("M336J H26 candidate pack changed while publishing")
    rows = _rows(destination)
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J_H26_PRODUCTION_REPORT",
        "exact_f26_sha": exact_f26_sha,
        "freeze_manifest_hash": manifest.manifest_hash,
        "candidate_pack_content_hash": pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": pack.candidate_pack_tree_hash,
        "published_file_count": len(rows),
        "published_tree_hash": content_hash(rows),
        "source_bearing_file_count": 0,
        "golden_file_count": 0,
        "private_artifact_count": 0,
        "status": "H26_READY_TO_COMMIT",
    }
    return {**body, "report_hash": content_hash(body)}


def stage_m336j_e26_publication(
    *,
    repository: Path,
    git_executable: Path,
    exact_f26_sha: str,
    exact_h26_sha: str,
    freeze_manifest: Path,
    evidence_source: Path,
    output: Path,
) -> dict:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    manifest = load_m336j_final_freeze_manifest_v2(freeze_manifest)
    _verify_clean_pushed_head(root, git, exact_h26_sha)
    if _git(git, root, "rev-parse", f"{exact_h26_sha}^{{commit}}^") != exact_f26_sha:
        raise ValueError("M336J E26 requires H26 parent to be exact F26")
    destination = output.resolve(strict=False)
    expected = (root / M336J3_E26_OUTPUT).resolve(strict=False)
    source = evidence_source.resolve(strict=True)
    if destination != expected or destination.exists() or source.is_relative_to(root):
        raise ValueError("M336J E26 publication paths are invalid")
    candidate_pack = root / M336J3_H26_OUTPUT / "candidate_pack"
    before = verify_java_public_candidate_pack(candidate_pack)
    destination.mkdir(parents=True)
    for item in sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix().encode("utf-8"),
    ):
        relative = item.relative_to(source)
        if item.suffix != ".json" or any(
            token in relative.as_posix().casefold()
            for token in ("golden", "private", "vault", ".java")
        ):
            raise ValueError("M336J E26 evidence source is not public-safe JSON")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
    _reject_private_payload(destination)
    _reject_public_json_payload(destination, reject_e26_identity=True)
    after = verify_java_public_candidate_pack(candidate_pack)
    if before != after:
        raise ValueError("M336J E26 changed the H26 candidate pack")
    rows = _rows(destination)
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J_E26_EVIDENCE_REPORT",
        "exact_f26_sha": exact_f26_sha,
        "exact_h26_sha": exact_h26_sha,
        "freeze_manifest_hash": manifest.manifest_hash,
        "candidate_pack_content_hash": before.candidate_pack_content_hash,
        "candidate_pack_tree_hash": before.candidate_pack_tree_hash,
        "published_evidence_file_count": len(rows),
        "published_evidence_tree_hash": content_hash(rows),
        "candidate_pack_change_count": 0,
        "source_leak_count": 0,
        "private_artifact_count": 0,
        "status": "E26_READY_TO_COMMIT",
    }
    return {**body, "report_hash": content_hash(body)}


def verify_m336j_h26_e26_commit_protocol(
    *,
    repository: Path,
    git_executable: Path,
    exact_f26_sha: str,
    exact_h26_sha: str,
    exact_e26_sha: str,
    freeze_manifest: Path,
) -> dict:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    manifest = load_m336j_final_freeze_manifest_v2(freeze_manifest)
    _verify_clean_pushed_head(root, git, exact_e26_sha)
    parents = (
        _git(git, root, "rev-parse", f"{exact_h26_sha}^{{commit}}^"),
        _git(git, root, "rev-parse", f"{exact_e26_sha}^{{commit}}^"),
    )
    h_paths = _diff_paths(git, root, exact_f26_sha, exact_h26_sha)
    e_paths = _diff_paths(git, root, exact_h26_sha, exact_e26_sha)
    invalid_h = tuple(
        path for path in h_paths if not path.startswith(M336J3_H26_OUTPUT.as_posix())
    )
    invalid_e = tuple(
        path for path in e_paths if not path.startswith(M336J3_E26_OUTPUT.as_posix())
    )
    candidate_changes = tuple(
        path
        for path in e_paths
        if path.startswith((M336J3_H26_OUTPUT / "candidate_pack").as_posix())
    )
    implementation = tuple(
        path
        for path in _diff_paths(git, root, exact_f26_sha, exact_e26_sha)
        if path.startswith(("src/", "scripts/", "tools/", "tests/", "schemas/"))
    )
    merge_count = int(
        _git(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{exact_f26_sha}..{exact_e26_sha}",
        )
    )
    subjects = (
        _git(git, root, "show", "-s", "--format=%s", exact_h26_sha),
        _git(git, root, "show", "-s", "--format=%s", exact_e26_sha),
    )
    if (
        parents != (exact_f26_sha, exact_h26_sha)
        or subjects != (M336J3_H26_SUBJECT, M336J3_E26_SUBJECT)
        or invalid_h
        or invalid_e
        or candidate_changes
        or implementation
        or merge_count
    ):
        raise ValueError("M336J H26/E26 commit protocol changed")
    body = {
        "schema_version": 2,
        "contract_role": "M336J_F26_H26_E26_COMMIT_PROTOCOL_RECEIPT",
        "exact_f26_sha": exact_f26_sha,
        "exact_h26_sha": exact_h26_sha,
        "exact_e26_sha": exact_e26_sha,
        "freeze_manifest_hash": manifest.manifest_hash,
        "h26_path_count": len(h_paths),
        "e26_path_count": len(e_paths),
        "implementation_change_count": 0,
        "candidate_pack_change_count": 0,
        "subject_binding_count": 2,
        "merge_count": 0,
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}


def _verify_clean_pushed_head(root: Path, git: Path, expected: str) -> None:
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    branch_ref = f"refs/heads/{_git(git, root, 'symbolic-ref', '--short', 'HEAD')}"
    remote = _git(git, root, "ls-remote", "--exit-code", "origin", branch_ref).split()
    if (
        head != expected
        or upstream != expected
        or len(remote) != 2
        or remote != [expected, branch_ref]
        or _git(git, root, "status", "--porcelain=v1")
    ):
        raise ValueError("M336J publisher requires clean pushed exact HEAD")


def _reject_private_payload(root: Path) -> None:
    bad = tuple(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.suffix.casefold() == ".java"
            or any(
                token in path.relative_to(root).as_posix().casefold()
                for token in ("golden", "private", "vault")
            )
        )
    )
    if bad:
        raise ValueError("M336J publication contains source, golden, or private data")


def _reject_public_json_payload(root: Path, *, reject_e26_identity: bool) -> None:
    """Reject public JSON that embeds host paths or a future E26 identity."""

    absolute_path = re.compile(r"(?:^|[\s\"'])[A-Za-z]:[\\/]|/(?:home|Users|root)/")

    def visit(value, *, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if not isinstance(child_key, str):
                    raise TypeError("M336J public JSON key is not text")
                if reject_e26_identity and child_key.casefold() in {
                    "e26_sha",
                    "exact_e26_sha",
                    "outcome_commit_sha",
                }:
                    raise ValueError("M336J E26 evidence is self-referential")
                visit(child, key=child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key=key)
        elif isinstance(value, str) and absolute_path.search(value):
            raise ValueError("M336J publication contains an absolute host path")

    for path in root.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("M336J publication contains invalid JSON") from error
        visit(value)


def _rows(root: Path) -> tuple[tuple[str, int, str], ...]:
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


def _diff_paths(git: Path, root: Path, left: str, right: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in _git(git, root, "diff", "--name-only", left, right).splitlines()
        if line
    )


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()

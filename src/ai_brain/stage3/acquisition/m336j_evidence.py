"""Non-self-referential Q25 qualification and commit evidence."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)

M336J_Q25_SUBJECT = "M-33.6j qualify exact non-interactive Karina route"
M336J_Q25_ALLOWED_PREFIXES = ("artifacts/m336j/", "docs/m336j_", "runs/m336j/")
M336J_QUALIFICATION_REQUIRED_FILES = frozenset(
    {
        "route_component_registry.json",
        "route_manifest.json",
        "public_execution_capsule_receipt.json",
        "python_environment_manifest.json",
        "executable_dependency_manifest.json",
        "schema_registry.json",
        "storage_capacity_receipt.json",
        "host_preflight_receipt.json",
        "remote_vault_transfer_receipt.json",
        "remote_inputs_transfer_receipt.json",
        "remote_materialization_receipt.json",
        "remote_production_receipt.json",
        "remote_download_receipt.json",
        "remote_replay_receipt.json",
        "remote_evaluation_receipt.json",
        "remote_runtime_receipt.json",
        "route_transcript.json",
        "streaming_transfer_receipt.json",
        "mutation_report.json",
        "windows_quality_receipt.json",
        "karina_quality_receipt.json",
        "windows_lineage_mutation_report.json",
        "karina_lineage_mutation_report.json",
        "final_unspent_receipt.json",
        "implementation_lineage_receipt.json",
    }
)
M336J_QUALIFICATION_EXCLUDED_NAMES = frozenset(
    {
        "readiness_result.json",
        "q25_tree_manifest.json",
        "q25_staging_receipt.json",
        "post_q25_commit_receipt.json",
    }
)


@dataclass(frozen=True)
class M336JEvidenceFile:
    relative_path: str
    byte_size: int
    bytes_hash: str


@dataclass(frozen=True)
class M336JQ25TreeManifest:
    schema_version: int
    contract_role: str
    exact_r25c_sha: str
    qualification_input_tree_hash: str
    qualification_input_file_count: int
    readiness_hash: str
    qualification_input_prefix: str
    readiness_relative_path: str
    self_excluded_names: tuple[str, ...]
    manifest_hash: str


@dataclass(frozen=True)
class M336JQ25StagingReceipt:
    schema_version: int
    contract_role: str
    exact_r25c_sha: str
    qualification_input_tree_hash: str
    readiness_hash: str
    files: tuple[M336JEvidenceFile, ...]
    file_count: int
    q25_staging_tree_hash: str
    post_scan_modified_file_count: int
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336JPostQ25CommitReceipt:
    schema_version: int
    contract_role: str
    exact_r25c_sha: str
    exact_q25_sha: str
    q25_parent_matches: bool
    q25_subject_matches: bool
    changed_path_count: int
    forbidden_changed_path_count: int
    implementation_diff_count: int
    merge_count: int
    prospective_tree_hash: str
    committed_tree_hash: str
    committed_file_mismatch_count: int
    post_scan_modified_file_count: int
    worktree_clean: bool
    status: str
    receipt_hash: str


def qualification_input_tree_rows(root: Path) -> tuple[M336JEvidenceFile, ...]:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("M336J qualification input root must be a directory")
    files = tuple(item for item in resolved.rglob("*") if item.is_file())
    top_level = {item.name for item in files if item.parent == resolved}
    missing = M336J_QUALIFICATION_REQUIRED_FILES - top_level
    excluded = {
        item.name for item in files if item.name in M336J_QUALIFICATION_EXCLUDED_NAMES
    }
    if missing or excluded:
        raise ValueError(
            "M336J qualification tree is incomplete or contains self-referential output"
        )
    return _tree_rows(resolved)


def qualification_input_tree_hash(root: Path) -> str:
    return content_hash(qualification_input_tree_rows(root))


def build_m336j_q25_staging(
    *,
    qualification_input_root: Path,
    readiness_result: Path,
    output_root: Path,
    exact_r25c_sha: str,
) -> M336JQ25StagingReceipt:
    """Build a final tree whose hash is kept in an external receipt."""

    source = qualification_input_root.resolve(strict=True)
    readiness_path = readiness_result.resolve(strict=True)
    output = output_root.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336J Q25 staging output must be fresh")
    qualification_rows = qualification_input_tree_rows(source)
    qualification_hash = content_hash(qualification_rows)
    readiness = strict_json_file(readiness_path)
    if not isinstance(readiness, dict):
        raise TypeError("M336J readiness result must be an object")
    readiness_body = dict(readiness)
    readiness_hash = readiness_body.pop("readiness_hash", None)
    if (
        content_hash(readiness_body) != readiness_hash
        or readiness.get("status") != "READY_FOR_HERMETIC_FINAL_ACQUISITION"
        or readiness.get("exact_r25_sha") != exact_r25c_sha
        or readiness.get("qualification_input_tree_hash") != qualification_hash
    ):
        raise ValueError("M336J readiness result does not bind qualification inputs")
    qualification_target = output / "artifacts/m336j/qualification-inputs"
    readiness_target = output / "runs/m336j/readiness_result.json"
    manifest_target = output / "artifacts/m336j/q25_tree_manifest.json"
    shutil.copytree(source, qualification_target)
    readiness_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(readiness_path, readiness_target)
    manifest_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_NON_SELF_REFERENTIAL_Q25_TREE_MANIFEST",
        "exact_r25c_sha": exact_r25c_sha,
        "qualification_input_tree_hash": qualification_hash,
        "qualification_input_file_count": len(qualification_rows),
        "readiness_hash": readiness_hash,
        "qualification_input_prefix": "artifacts/m336j/qualification-inputs/",
        "readiness_relative_path": "runs/m336j/readiness_result.json",
        "self_excluded_names": tuple(sorted(M336J_QUALIFICATION_EXCLUDED_NAMES)),
    }
    manifest = M336JQ25TreeManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    write_canonical_json(manifest_target, manifest)
    first = _tree_rows(output)
    second = _tree_rows(output)
    modified = 0 if first == second else 1
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_Q25_STAGING_RECEIPT",
        "exact_r25c_sha": exact_r25c_sha,
        "qualification_input_tree_hash": qualification_hash,
        "readiness_hash": readiness_hash,
        "files": second,
        "file_count": len(second),
        "q25_staging_tree_hash": content_hash(second),
        "post_scan_modified_file_count": modified,
        "status": "PASS" if not modified else "FAIL",
    }
    receipt = M336JQ25StagingReceipt(**body, receipt_hash=content_hash(body))
    if receipt.status != "PASS":
        raise ValueError("M336J Q25 staging changed during its final scan")
    return receipt


def q25_staging_receipt_from_dict(value: dict) -> M336JQ25StagingReceipt:
    if not isinstance(value, dict) or set(value) != {
        item.name for item in fields(M336JQ25StagingReceipt)
    }:
        raise ValueError("M336J Q25 staging receipt fields changed")
    converted = dict(value)
    raw_files = converted.get("files")
    if not isinstance(raw_files, list):
        raise TypeError("M336J Q25 staging file rows changed")
    rows = []
    for raw in raw_files:
        if not isinstance(raw, dict) or set(raw) != {
            item.name for item in fields(M336JEvidenceFile)
        }:
            raise ValueError("M336J Q25 staging file row changed")
        rows.append(M336JEvidenceFile(**raw))
    converted["files"] = tuple(rows)
    receipt = M336JQ25StagingReceipt(**converted)
    _verify_q25_staging_receipt(receipt)
    return receipt


def _verify_q25_staging_receipt(receipt: M336JQ25StagingReceipt) -> None:
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.status != "PASS"
        or receipt.file_count != len(receipt.files)
        or receipt.post_scan_modified_file_count
        or receipt.q25_staging_tree_hash != content_hash(receipt.files)
        or content_hash(body) != claimed
    ):
        raise ValueError("M336J Q25 staging receipt is invalid")


def verify_m336j_post_q25_commit(
    *,
    repository: Path,
    git_executable: Path,
    staging_root: Path,
    staging_receipt: M336JQ25StagingReceipt,
    exact_r25c_sha: str,
    exact_q25_sha: str,
) -> M336JPostQ25CommitReceipt:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    stage = staging_root.resolve(strict=True)
    _verify_q25_staging_receipt(staging_receipt)
    head = _git_text(git, root, "rev-parse", "HEAD^{commit}")
    parent_tokens = _git_text(
        git, root, "rev-list", "--parents", "-n", "1", exact_q25_sha
    ).split()
    parent_matches = parent_tokens == [exact_q25_sha, exact_r25c_sha]
    subject_matches = (
        _git_text(git, root, "show", "-s", "--format=%s", exact_q25_sha)
        == M336J_Q25_SUBJECT
    )
    changed = tuple(
        item
        for item in _git_text(
            git, root, "diff", "--name-only", f"{exact_r25c_sha}..{exact_q25_sha}"
        ).splitlines()
        if item
    )
    forbidden = tuple(
        item for item in changed if not item.startswith(M336J_Q25_ALLOWED_PREFIXES)
    )
    expected_paths = tuple(row.relative_path for row in staging_receipt.files)
    current_rows = _tree_rows(stage)
    post_scan_modified = int(current_rows != staging_receipt.files)
    committed_rows = []
    mismatch_count = 0
    for row in staging_receipt.files:
        raw = _git_bytes(git, root, "show", f"{exact_q25_sha}:{row.relative_path}")
        committed = M336JEvidenceFile(
            relative_path=row.relative_path,
            byte_size=len(raw),
            bytes_hash=bytes_hash(raw),
        )
        committed_rows.append(committed)
        mismatch_count += committed != row
    committed_rows_tuple = tuple(committed_rows)
    merge_count = int(
        _git_text(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{exact_r25c_sha}..{exact_q25_sha}",
        )
    )
    clean = not _git_text(git, root, "status", "--porcelain=v1")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_POST_Q25_COMMIT_RECEIPT",
        "exact_r25c_sha": exact_r25c_sha,
        "exact_q25_sha": exact_q25_sha,
        "q25_parent_matches": parent_matches,
        "q25_subject_matches": subject_matches,
        "changed_path_count": len(changed),
        "forbidden_changed_path_count": len(forbidden),
        "implementation_diff_count": len(forbidden),
        "merge_count": merge_count,
        "prospective_tree_hash": staging_receipt.q25_staging_tree_hash,
        "committed_tree_hash": content_hash(committed_rows_tuple),
        "committed_file_mismatch_count": mismatch_count,
        "post_scan_modified_file_count": post_scan_modified,
        "worktree_clean": clean,
        "status": "PASS",
    }
    valid = (
        head == exact_q25_sha
        and parent_matches
        and subject_matches
        and not forbidden
        and not merge_count
        and not mismatch_count
        and not post_scan_modified
        and tuple(changed) == expected_paths
        and body["committed_tree_hash"] == staging_receipt.q25_staging_tree_hash
        and clean
    )
    if not valid:
        raise ValueError("M336J post-Q25 committed tree verification failed")
    return M336JPostQ25CommitReceipt(**body, receipt_hash=content_hash(body))


def _tree_rows(root: Path) -> tuple[M336JEvidenceFile, ...]:
    return tuple(
        M336JEvidenceFile(
            relative_path=path.relative_to(root).as_posix(),
            byte_size=path.stat().st_size,
            bytes_hash=bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode(),
        )
    )


def _git_text(git: Path, repository: Path, *arguments: str) -> str:
    return _git_bytes(git, repository, *arguments).decode("utf-8").strip()


def _git_bytes(git: Path, repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout


def validate_q25_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("M336J Q25 evidence path is unsafe")

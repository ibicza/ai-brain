"""Fail-closed stale project-artifact cleanup for M-33.6k.5."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

M336K5_CLEANUP_CATEGORIES = frozenset(
    {
        "CLEAN_GIT_WORKTREE",
        "DISPOSABLE_PROTOCOL_CLONE",
        "EXACT_QUALITY_BASETEMP",
        "COMPILER_OUTPUT",
        "REPLAY_OUTPUT",
        "EVALUATOR_GOLDEN_OUTPUT",
        "STAGING_TREE",
        "TRANSFER_ARCHIVE",
        "DUPLICATE_DISPOSABLE_VAULT",
        "PYTEST_CACHE",
        "RUFF_CACHE",
        "PYTHON_BYTECODE_CACHE",
        "CODE_GRAPH_CACHE_GENERATION",
        "ORPHANED_TERMINAL_WORKER",
    }
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MARKER = ".m336k5-project-generated.json"


@dataclass(frozen=True)
class M336K5CleanupAssessment:
    schema_version: int
    contract_role: str
    opaque_root_id: str
    category: str
    terminal_run_id_hash: str
    tree_hash: str
    file_count: int
    byte_count: int
    project_generated: bool
    active_process_count: int
    open_file_count: int
    active_ledger_reference_count: int
    current_route_reference_count: int
    unique_evidence_count: int
    preservation_intersection_count: int
    unique_uncommitted_count: int
    reparse_point_count: int
    eligible: bool
    assessment_hash: str

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 cleanup assessment fields changed")
        result = cls(**value)
        verify_m336k5_cleanup_assessment(result)
        return result


@dataclass(frozen=True)
class M336K5CleanupReceipt:
    schema_version: int
    contract_role: str
    opaque_root_id: str
    category: str
    assessment_hash: str
    tree_hash: str
    deleted_file_count: int
    reclaimed_bytes: int
    target_absent: bool
    status: str
    receipt_hash: str


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalized_roots(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(path.resolve(strict=False) for path in paths)


def write_m336k5_project_generated_marker(
    root: Path, *, category: str, terminal_run_id: str
) -> str:
    if category not in M336K5_CLEANUP_CATEGORIES or not terminal_run_id:
        raise M336K2ProtocolError("M336K5 cleanup marker input is invalid")
    destination = root.resolve(strict=True) / _MARKER
    if destination.exists():
        raise FileExistsError("M336K5 cleanup marker already exists")
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PROJECT_GENERATED_ROOT",
        "category": category,
        "terminal_run_id_hash": content_hash(("M336K5_RUN_ID", terminal_run_id)),
        "terminal": True,
    }
    value = {**body, "marker_hash": content_hash(body)}
    with destination.open("xb") as stream:
        stream.write(_canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    return value["marker_hash"]


def _read_marker(root: Path, category: str) -> tuple[bool, str]:
    marker = root / _MARKER
    try:
        raw = marker.read_bytes()
        if not raw.endswith(b"\n") or raw.endswith(b"\r\n"):
            return False, "0" * 64
        value = json.loads(raw)
    except (FileNotFoundError, OSError, ValueError):
        return False, "0" * 64
    if type(value) is not dict:
        return False, "0" * 64
    body = dict(value)
    claimed = body.pop("marker_hash", None)
    run_hash = body.get("terminal_run_id_hash")
    valid = (
        set(body)
        == {
            "schema_version",
            "contract_role",
            "category",
            "terminal_run_id_hash",
            "terminal",
        }
        and value["schema_version"] == 1
        and value["contract_role"] == "M336K5_PROJECT_GENERATED_ROOT"
        and value["category"] == category
        and value["terminal"] is True
        and isinstance(run_hash, str)
        and _HASH.fullmatch(run_hash) is not None
        and content_hash(body) == claimed
    )
    return valid, run_hash if valid else "0" * 64


def _tree_inventory(root: Path) -> tuple[str, int, int, int]:
    rows: list[tuple[str, int, str]] = []
    reparse_points = 0
    for current, directories, files in os.walk(root, topdown=True):
        current_path = Path(current)
        for name in sorted((*directories, *files)):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            stat = path.lstat()
            attributes = getattr(stat, "st_file_attributes", 0)
            if path.is_symlink() or attributes & 0x400:
                reparse_points += 1
                continue
            if path.is_file():
                rows.append((relative, stat.st_size, bytes_hash(path.read_bytes())))
    return content_hash(rows), len(rows), sum(row[1] for row in rows), reparse_points


def assess_m336k5_cleanup_candidate(
    root: Path,
    *,
    category: str,
    allowed_base_roots: Iterable[Path],
    preservation_paths: Iterable[Path] = (),
    active_process_paths: Iterable[Path] = (),
    open_file_paths: Iterable[Path] = (),
    active_ledger_paths: Iterable[Path] = (),
    current_route_paths: Iterable[Path] = (),
    unique_evidence_paths: Iterable[Path] = (),
    unique_uncommitted_paths: Iterable[Path] = (),
) -> M336K5CleanupAssessment:
    target = root.resolve(strict=True)
    allowed = _normalized_roots(allowed_base_roots)
    if (
        category not in M336K5_CLEANUP_CATEGORIES
        or not target.is_dir()
        or not any(target != base and _is_relative_to(target, base) for base in allowed)
    ):
        raise M336K2ProtocolError("M336K5 cleanup target escaped allowed roots")
    project_generated, terminal_run_id_hash = _read_marker(target, category)
    tree_hash, file_count, byte_count, reparse_points = _tree_inventory(target)

    def intersections(paths: Iterable[Path]) -> int:
        count = 0
        for item in _normalized_roots(paths):
            if _is_relative_to(item, target) or _is_relative_to(target, item):
                count += 1
        return count

    counts = {
        "active_process_count": intersections(active_process_paths),
        "open_file_count": intersections(open_file_paths),
        "active_ledger_reference_count": intersections(active_ledger_paths),
        "current_route_reference_count": intersections(current_route_paths),
        "unique_evidence_count": intersections(unique_evidence_paths),
        "preservation_intersection_count": intersections(preservation_paths),
        "unique_uncommitted_count": intersections(unique_uncommitted_paths),
        "reparse_point_count": reparse_points,
    }
    eligible = project_generated and all(value == 0 for value in counts.values())
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_CLEANUP_ASSESSMENT",
        "opaque_root_id": content_hash(("M336K5_CLEANUP_ROOT", str(target))),
        "category": category,
        "terminal_run_id_hash": terminal_run_id_hash,
        "tree_hash": tree_hash,
        "file_count": file_count,
        "byte_count": byte_count,
        "project_generated": project_generated,
        **counts,
        "eligible": eligible,
    }
    result = M336K5CleanupAssessment(**body, assessment_hash=content_hash(body))
    verify_m336k5_cleanup_assessment(result)
    return result


def verify_m336k5_cleanup_assessment(
    assessment: M336K5CleanupAssessment,
) -> None:
    body = asdict(assessment)
    claimed = body.pop("assessment_hash")
    counts = (
        assessment.file_count,
        assessment.byte_count,
        assessment.active_process_count,
        assessment.open_file_count,
        assessment.active_ledger_reference_count,
        assessment.current_route_reference_count,
        assessment.unique_evidence_count,
        assessment.preservation_intersection_count,
        assessment.unique_uncommitted_count,
        assessment.reparse_point_count,
    )
    blockers = counts[2:]
    if (
        assessment.schema_version != 1
        or assessment.contract_role != "M336K5_CLEANUP_ASSESSMENT"
        or assessment.category not in M336K5_CLEANUP_CATEGORIES
        or any(
            _HASH.fullmatch(value) is None
            for value in (
                assessment.opaque_root_id,
                assessment.terminal_run_id_hash,
                assessment.tree_hash,
                assessment.assessment_hash,
            )
        )
        or any(value < 0 for value in counts)
        or assessment.eligible != (assessment.project_generated and not any(blockers))
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K5 cleanup assessment is invalid")


def delete_m336k5_cleanup_candidate(
    root: Path, assessment: M336K5CleanupAssessment
) -> M336K5CleanupReceipt:
    verify_m336k5_cleanup_assessment(assessment)
    target = root.resolve(strict=True)
    opaque_root_id = content_hash(("M336K5_CLEANUP_ROOT", str(target)))
    tree_hash, file_count, byte_count, reparse_points = _tree_inventory(target)
    if (
        not assessment.eligible
        or opaque_root_id != assessment.opaque_root_id
        or tree_hash != assessment.tree_hash
        or file_count != assessment.file_count
        or byte_count != assessment.byte_count
        or reparse_points
    ):
        raise M336K2ProtocolError("M336K5 cleanup target changed after assessment")
    shutil.rmtree(target, onexc=_remove_readonly)
    absent = not target.exists()
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_CLEANUP_DELETION_RECEIPT",
        "opaque_root_id": opaque_root_id,
        "category": assessment.category,
        "assessment_hash": assessment.assessment_hash,
        "tree_hash": tree_hash,
        "deleted_file_count": file_count,
        "reclaimed_bytes": byte_count,
        "target_absent": absent,
        "status": "PASS" if absent else "FAIL",
    }
    return M336K5CleanupReceipt(**body, receipt_hash=content_hash(body))


def _remove_readonly(function, path: str, error: BaseException) -> None:
    if not isinstance(error, PermissionError):
        raise error
    os.chmod(path, stat.S_IWRITE)
    function(path)

"""Cross-platform comparison rules for M-33.6e production evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

# These receipts intentionally bind the executing host or platform.  They are
# compared semantically by the production seals and Q20 assembler, not as
# byte-identical platform-neutral artifacts.
HOST_BOUND_PRODUCTION_ARTIFACTS = frozenset(
    {
        "production_performance.json",
        "production_process_audit.json",
        "production_file_access_audit.json",
        "production_state_audit.json",
        "m336d_production_seal.json",
        "m336e_production_execution.json",
        "production_summary.json",
    }
)


def compare_m336e_production_trees(
    windows_root: Path,
    karina_root: Path,
) -> dict[str, Any]:
    """Compare every M-33.6e production artifact not declared host-bound."""

    windows = _rows(windows_root.resolve(strict=True))
    karina = _rows(karina_root.resolve(strict=True))
    paths = tuple(sorted(set(windows) | set(karina)))
    differences = tuple(
        path
        for path in paths
        if path not in HOST_BOUND_PRODUCTION_ARTIFACTS
        and windows.get(path) != karina.get(path)
    )
    body = {
        "schema_version": 2,
        "host_bound_artifacts": tuple(
            path for path in paths if path in HOST_BOUND_PRODUCTION_ARTIFACTS
        ),
        "platform_neutral_artifact_count": sum(
            path not in HOST_BOUND_PRODUCTION_ARTIFACTS for path in paths
        ),
        "platform_independent_difference_count": len(differences),
        "different_paths": differences,
        "windows_tree_hash": content_hash(tuple(sorted(windows.items()))),
        "karina_tree_hash": content_hash(tuple(sorted(karina.items()))),
        "status": "PASS" if not differences else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _rows(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): bytes_hash(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }

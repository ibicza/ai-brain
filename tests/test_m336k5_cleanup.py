from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_cleanup import (
    assess_m336k5_cleanup_candidate,
    delete_m336k5_cleanup_candidate,
    write_m336k5_project_generated_marker,
)


def _generated_root(tmp_path: Path) -> Path:
    root = tmp_path / "m336k5-disposable-complete"
    root.mkdir()
    (root / "receipt.json").write_text("{}\n", encoding="utf-8")
    write_m336k5_project_generated_marker(
        root,
        category="DISPOSABLE_PROTOCOL_CLONE",
        terminal_run_id="disposable-complete",
    )
    return root


def test_marked_terminal_root_can_be_deleted(tmp_path: Path) -> None:
    root = _generated_root(tmp_path)
    assessment = assess_m336k5_cleanup_candidate(
        root,
        category="DISPOSABLE_PROTOCOL_CLONE",
        allowed_base_roots=(tmp_path,),
    )
    assert assessment.eligible
    receipt = delete_m336k5_cleanup_candidate(root, assessment)
    assert receipt.status == "PASS"
    assert receipt.target_absent
    assert receipt.reclaimed_bytes > 0


def test_marked_terminal_root_with_readonly_file_can_be_deleted(
    tmp_path: Path,
) -> None:
    root = _generated_root(tmp_path)
    protected = root / "readonly.pack"
    protected.write_bytes(b"immutable disposable pack")
    os.chmod(protected, stat.S_IREAD)
    assessment = assess_m336k5_cleanup_candidate(
        root,
        category="DISPOSABLE_PROTOCOL_CLONE",
        allowed_base_roots=(tmp_path,),
    )
    receipt = delete_m336k5_cleanup_candidate(root, assessment)
    assert receipt.status == "PASS"
    assert not root.exists()


@pytest.mark.parametrize(
    "blocker",
    (
        "preservation_paths",
        "active_process_paths",
        "open_file_paths",
        "active_ledger_paths",
        "current_route_paths",
        "unique_evidence_paths",
        "unique_uncommitted_paths",
    ),
)
def test_cleanup_rejects_every_safety_blocker(tmp_path: Path, blocker: str) -> None:
    root = _generated_root(tmp_path)
    assessment = assess_m336k5_cleanup_candidate(
        root,
        category="DISPOSABLE_PROTOCOL_CLONE",
        allowed_base_roots=(tmp_path,),
        **{blocker: (root,)},
    )
    assert not assessment.eligible
    with pytest.raises(M336K2ProtocolError):
        delete_m336k5_cleanup_candidate(root, assessment)
    assert root.exists()


def test_unmarked_or_reparse_root_is_not_eligible(tmp_path: Path) -> None:
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    assessment = assess_m336k5_cleanup_candidate(
        unmarked,
        category="DISPOSABLE_PROTOCOL_CLONE",
        allowed_base_roots=(tmp_path,),
    )
    assert not assessment.eligible

    marked = _generated_root(tmp_path)
    link = marked / "escape"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    assessment = assess_m336k5_cleanup_candidate(
        marked,
        category="DISPOSABLE_PROTOCOL_CLONE",
        allowed_base_roots=(tmp_path,),
    )
    assert not assessment.eligible

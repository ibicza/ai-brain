"""Cross-iteration held-out ownership must survive newly discovered duplicates."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "expand_prepare", ROOT / "scripts/m33_objects_expand_prepare.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(identity, split=None, answer="яблоко"):
    return {
        "source_id": identity,
        "answer": answer,
        "parent": split is not None,
        "split": split,
    }


def test_new_duplicate_of_known_final_remains_regression():
    assigned, excluded, fresh = module.assign_groups(
        [row("old", "regression"), row("new")], [0, 0]
    )
    assert {split for _, split, _ in assigned} == {"regression"}
    assert not excluded and not fresh


def test_bridge_between_prior_owners_quarantines_whole_family():
    assigned, excluded, _ = module.assign_groups(
        [row("old-train", "train"), row("old-final", "regression"), row("new")],
        [0, 0, 0],
    )
    assert not assigned
    assert {r["source_id"] for r in excluded} == {"old-train", "old-final", "new"}


def test_conflicting_labels_are_not_silently_relabelled():
    assigned, excluded, _ = module.assign_groups(
        [row("a"), row("b", answer="UNKNOWN")], [0, 0]
    )
    assert not assigned and len(excluded) == 2


def test_fresh_family_partitioning_deterministic_and_no_split_leakage():
    records = [row(str(i)) for i in range(40)]
    first = module.assign_groups(records, list(range(40)))
    assert first == module.assign_groups(records, list(range(40)))
    assigned, excluded, fresh = first
    assert not excluded and fresh == {"яблоко": 40}
    assert len({identity for _, _, identity in assigned}) == 40
    assert {
        split: sum(owner == split for _, owner, _ in assigned)
        for split in ("train", "dev", "calibration", "final")
    } == {"train": 24, "dev": 4, "calibration": 6, "final": 6}


def test_photo_only_round_keeps_sketch_lineage_for_a_later_mixed_expansion():
    parent = {"acquisition_sha256": "a" * 64, "licence_snapshot_sha256": "b" * 64}
    assert module.retained_sketch_lineage(parent) == ("a" * 64, "b" * 64)
    with pytest.raises(ValueError, match="sketch provenance"):
        module.retained_sketch_lineage(parent | {"acquisition_sha256": None})

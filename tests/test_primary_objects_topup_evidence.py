import hashlib
import os
import zipfile

import pytest
from m33_objects_topup_evidence import bundle_parts, record_once


def test_identical_receipt_retry_is_idempotent(tmp_path):
    path = tmp_path / "receipt.json"
    record_once(path, {"files": [1, 2], "verified": True})
    before = path.read_bytes()
    record_once(path, {"files": [1, 2], "verified": True})
    assert path.read_bytes() == before


def test_changed_receipt_retry_preserves_original(tmp_path):
    path = tmp_path / "receipt.json"
    record_once(path, {"files": [1, 2]})
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Receipt differs"):
        record_once(path, {"files": [1, 2, 3]})
    assert path.read_bytes() == before


def test_archive_parts_restore_exact_bytes(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    destination = tmp_path / "archive"
    bundles = bundle_parts(destination, [(first, "a"), (second, "nested/b")], limit=7)
    assert len(bundles) == 2
    for part in bundles:
        with zipfile.ZipFile(destination / part["file"]) as archive:
            for entry in part["entries"]:
                assert (
                    hashlib.sha256(archive.read(entry["file"])).hexdigest()
                    == entry["sha256"]
                )
    with pytest.raises(ValueError, match="Fresh"):
        bundle_parts(destination, [(first, "a")])


@pytest.mark.parametrize(
    "names", [("same", "same"), ("../escape", "ok"), ("/root", "ok"), ("a\\b", "ok")]
)
def test_unsafe_restore_paths_rejected_before_creation(tmp_path, names):
    first = tmp_path / "source"
    first.write_bytes(b"safe")
    destination = tmp_path / "archive"
    with pytest.raises(ValueError, match="Unsafe"):
        bundle_parts(destination, [(first, names[0]), (first, names[1])])
    assert not destination.exists()


def test_oversized_source_rejected_before_creation(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"12345678")
    destination = tmp_path / "archive"
    with pytest.raises(ValueError, match="Individual"):
        bundle_parts(destination, [(source, "source")], limit=7)
    assert not destination.exists()


def test_pre_zip_epoch_timestamp_does_not_change_source_bytes(tmp_path):
    source = tmp_path / "old-capsule-member"
    source.write_bytes(b"unchanged training source")
    os.utime(source, (0, 0))
    bundles = bundle_parts(tmp_path / "archive", [(source, "source")])
    with zipfile.ZipFile(tmp_path / "archive" / bundles[0]["file"]) as archive:
        assert archive.read("source") == source.read_bytes()
        assert archive.getinfo("source").date_time[0] == 1980

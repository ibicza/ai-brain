"""Backup chunk integrity without touching a Git ref or user data."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "m33_composition_sixhour_backup",
    Path(__file__).parents[1] / "scripts/m33_composition_sixhour_backup.py",
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_scoped_backup_preserves_current_overview_and_both_work_journals():
    required = {
        "docs/m33_primary_composition.md",
        "docs/m33_primary_composition_continuation.md",
        "docs/m33_composition_six_hour_work.md",
        "docs/m33_composition_balanced_foreground.md",
        "src/ai_brain/training/primary_composition_supervision.py",
        "tests/test_primary_composition_supervision.py",
    }
    assert required.issubset(backup.SOURCE_FILES)
    assert len(backup.SOURCE_FILES) == len(set(backup.SOURCE_FILES))
    assert not any(".code-review-graph/" in name for name in backup.SOURCE_FILES)


def test_original_large_file_is_reconstructed_from_ordered_hash_bound_chunks(tmp_path):
    source = tmp_path / "original.bin"
    original = bytes(range(256)) * 17 + b"tail"
    source.write_bytes(original)
    output = tmp_path / "chunks"
    report = backup.chunks(source, output, limit=500)
    assert all(p["bytes"] <= 500 for p in report["parts"])
    assert (
        b"".join((output / p["file"]).read_bytes() for p in report["parts"]) == original
    )
    assert report["sha256"] == backup.sha(source)
    assert report["bytes"] == len(original)
    for part in report["parts"]:
        assert backup.sha(output / part["file"]) == part["sha256"]
    with pytest.raises(ValueError, match="Fresh"):
        backup.chunks(source, output, limit=500)
    assert source.read_bytes() == original


@pytest.mark.parametrize("limit", (0, -1, True, 1.5, 32 * 1024 * 1024 + 1))
def test_unsafe_chunk_size_is_rejected_before_output(tmp_path, limit):
    source = tmp_path / "original.bin"
    source.write_bytes(b"data")
    output = tmp_path / "chunks"
    with pytest.raises(ValueError, match="Fresh"):
        backup.chunks(source, output, limit=limit)
    assert not output.exists()


def test_direct_git_chunks_reconstruct_original_without_disk_duplicate(tmp_path):
    import hashlib

    original = b"abc" * 1000 + b"tail"
    source = tmp_path / "original.bin"
    source.write_bytes(original)
    blobs = {}

    def put(block):
        blob = hashlib.sha1(
            b"blob " + str(len(block)).encode() + b"\0" + block
        ).hexdigest()
        blobs[blob] = block
        return blob

    report = backup.git_chunks(source, put, blobs.__getitem__, limit=500)
    assert b"".join(blobs[p["blob_id"]] for p in report["parts"]) == original
    assert report["sha256"] == backup.sha(source)
    assert report["storage"] == "git_blobs_no_temporary_chunk_copy"
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == original


@pytest.mark.parametrize("limit", (0, -1, True, 1.5, 32 * 1024 * 1024 + 1))
def test_direct_git_chunk_limit_is_checked_before_writing(tmp_path, limit):
    source = tmp_path / "original.bin"
    source.write_bytes(b"original")
    with pytest.raises(ValueError, match="bounded chunk"):
        backup.git_chunks(
            source, lambda _: pytest.fail("No blob write allowed"), None, limit=limit
        )


def test_direct_git_chunks_reject_wrong_stored_bytes(tmp_path):
    source = tmp_path / "original.bin"
    source.write_bytes(b"original")
    with pytest.raises(ValueError, match="Git blob bytes differ"):
        backup.git_chunks(source, lambda _: "a" * 40, lambda _: b"wrong")


def test_direct_git_chunks_detect_source_mutation_during_storage(tmp_path):
    source = tmp_path / "original.bin"
    source.write_bytes(b"original")
    saved = []

    def put(block):
        saved.append(block)
        source.write_bytes(b"tampered")
        return "a" * 40

    with pytest.raises(ValueError, match="reconstructed Git chunk bytes"):
        backup.git_chunks(source, put, lambda _: saved[0])


def test_direct_chunks_use_real_git_blobs_and_restore_exact_bytes(tmp_path):
    import subprocess

    bare = tmp_path / "isolated.git"
    subprocess.run(
        ["git", "init", "--bare", "--object-format=sha1", str(bare)],
        capture_output=True,
        check=True,
    )
    prefix = ["git", "--git-dir=" + str(bare)]
    source = tmp_path / "original.bin"
    original = bytes(range(256)) * 17 + b"tail"
    source.write_bytes(original)

    def put(block):
        return (
            subprocess.run(
                prefix + ["hash-object", "--no-filters", "-w", "--stdin"],
                input=block,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )

    def get(blob):
        return subprocess.run(
            prefix + ["cat-file", "blob", blob], capture_output=True, check=True
        ).stdout

    report = backup.git_chunks(source, put, get, limit=500)
    assert b"".join(get(p["blob_id"]) for p in report["parts"]) == original
    assert report["sha256"] == backup.sha(source)
    assert set(tmp_path.iterdir()) == {bare, source}

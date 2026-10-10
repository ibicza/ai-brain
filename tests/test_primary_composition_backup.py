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

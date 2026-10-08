"""Source preservation, multipart streaming, and restore confinement tests."""

import hashlib
import importlib.util
import io
import stat
import zipfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "lexicon_archive", Path(__file__).parents[1] / "scripts/lexicon_corpus_archive.py"
)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


@pytest.mark.parametrize(
    "name",
    [
        "../bad",
        "/absolute",
        "C:/bad",
        "a\\b",
        "a/../b",
        "a//b",
        "CON.txt",
        "a/.",
        "trailing.",
    ],
)
def test_unsafe_member_names(name):
    with pytest.raises(ValueError):
        archive.safe_name(name)


def test_utf8_multipart_archive_and_restore(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "empty").mkdir()
    (root / "рисунок.txt").write_text("Яблоко\n", encoding="utf-8")
    (root / "data.bin").write_bytes(bytes(range(256)) * 100)
    output = tmp_path / "archive"
    receipt = archive.create(root, output)
    assert receipt["source_files"] == 2
    assert receipt["source_before_after_identity_verified"] is True
    metadata, inventory, paths = archive.verify_parts(output / "parts-manifest.json")
    assert metadata["parts"][0]["bytes"] <= 40 * 1024 * 1024
    with archive.PartsReader(paths) as reader:
        assert reader.read() == (output / "corpus.zip").read_bytes()
        reader.seek(0)
        restored = archive.verify_zip(reader, inventory, tmp_path / "restored")
    assert restored["restored"] is True
    assert (tmp_path / "restored" / "рисунок.txt").read_bytes() == (
        root / "рисунок.txt"
    ).read_bytes()
    assert (tmp_path / "restored" / "empty").is_dir()
    with (
        archive.PartsReader(paths) as reader,
        pytest.raises(ValueError, match="new or empty"),
    ):
        archive.verify_zip(reader, inventory, tmp_path / "restored")
    original_part = paths[0].read_bytes()
    paths[0].write_bytes(original_part + b"corrupt")
    with pytest.raises(ValueError):
        archive.verify_parts(output / "parts-manifest.json")


def test_reader_crosses_part_boundaries(tmp_path):
    paths = [tmp_path / "a", tmp_path / "b", tmp_path / "c"]
    for path, data in zip(paths, [b"abc", b"de", b"fghi"], strict=True):
        path.write_bytes(data)
    with archive.PartsReader(paths) as reader:
        reader.seek(2)
        assert reader.read(5) == b"cdefg"
        reader.seek(-3, 2)
        assert reader.read() == b"ghi"
        reader.seek(0)
        assert reader.read() == b"abcdefghi"


def test_unsafe_zip_and_symlink_are_rejected_before_restore(tmp_path):
    for name, mode in [("../evil", stat.S_IFREG), ("link", stat.S_IFLNK)]:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as writer:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            writer.writestr(info, b"evil")
        stream.seek(0)
        inventory = {
            "files": [
                {
                    "path": name,
                    "bytes": 4,
                    "sha256": hashlib.sha256(b"evil").hexdigest(),
                    "mtime_ns": 0,
                }
            ],
            "directories": [],
            "total_bytes": 4,
        }
        destination = tmp_path / "restore"
        with pytest.raises(ValueError):
            archive.verify_zip(stream, inventory, destination)
        assert not destination.exists()


def test_inventory_collision_and_source_inside_output_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file").write_bytes(b"data")
    with pytest.raises(ValueError):
        archive.create(root, root / "archive")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as writer:
        writer.writestr("A", b"1")
        writer.writestr("a", b"1")
    stream.seek(0)
    item = {"bytes": 1, "sha256": hashlib.sha256(b"1").hexdigest(), "mtime_ns": 0}
    inventory = {
        "files": [{"path": "A", **item}, {"path": "a", **item}],
        "directories": [],
        "total_bytes": 2,
    }
    with pytest.raises(ValueError, match="collision"):
        archive.verify_zip(stream, inventory)

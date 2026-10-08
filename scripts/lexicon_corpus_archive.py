"""Hash-audit a draft corpus and preserve every file in verified split ZIPs.

No training, source mutations or Git operations. Archive-only superseded files
remain recoverable but must not re-enter the effective visual catalogue.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

CHUNK = 1024 * 1024
MAX_PART_BYTES = 40 * CHUNK


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            value.update(chunk)
    return value.hexdigest()


def save(path: Path, value: dict) -> None:
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)


def safe_name(name: str) -> str:
    value = name.removesuffix("/")
    pieces = value.split("/")
    forbidden = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
    if not value or PurePosixPath(value).is_absolute() or "\\" in value or ":" in value:
        raise ValueError("unsafe archive path")
    if any(
        p in ("", ".", "..")
        or p.endswith((" ", "."))
        or p.split(".")[0].casefold() in forbidden
        or any(ord(c) < 32 for c in p)
        for p in pieces
    ):
        raise ValueError("unsafe archive path component")
    return value


def collect(root: Path) -> tuple[list[dict], list[str]]:
    files, directories = [], []
    for current, subdirectories, filenames in os.walk(root, followlinks=False):
        for name in [*subdirectories, *filenames]:
            path = Path(current) / name
            details = path.lstat()
            if path.is_symlink() or getattr(details, "st_file_attributes", 0) & 0x400:
                raise ValueError(
                    f"symlink or reparse point requires explicit handling: {path}"
                )
            if not path.resolve().is_relative_to(root):
                raise ValueError("path escapes corpus")
            relative = safe_name(path.relative_to(root).as_posix())
            if path.is_dir():
                directories.append(relative)
            elif path.is_file():
                files.append(
                    {
                        "path": relative,
                        "bytes": details.st_size,
                        "sha256": digest(path),
                        "mtime_ns": details.st_mtime_ns,
                    }
                )
            else:
                raise ValueError(f"unsupported source object: {path}")
    return sorted(files, key=lambda item: item["path"]), sorted(directories)


def audit_merge(merge_path: Path, root: Path) -> dict:
    """Independent stdlib validation; does not reuse the merger implementation."""
    merged = json.loads(merge_path.read_text(encoding="utf-8"))
    raw = json.loads((root / "report.json").read_text(encoding="utf-8"))
    replacement = json.loads(
        (root / "geometry-corrections/replacement-index.json").read_text(
            encoding="utf-8"
        )
    )
    superseded = json.loads(
        (root / "effective-coverage-report.json").read_text(encoding="utf-8")
    )["superseded_unusable_media"]
    blocked = {(root / item["page_preview"]["path"]).resolve() for item in superseded}
    blocked.update(
        (root / image["path"]).resolve()
        for item in superseded
        for image in item["images"]
    )
    assets = {}
    for asset in merged["raw_assets"]:
        path = Path(asset["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path in blocked:
            raise ValueError(f"invalid or superseded current raw asset: {path}")
        if path in assets and assets[path] != asset["sha256"]:
            raise ValueError("conflicting asset hash")
        if digest(path) != asset["sha256"]:
            raise ValueError(f"raw asset hash mismatch: {path}")
        assets[path] = asset["sha256"]
    for row in merged["media"]:
        for column in (2, 13):
            if row[column] and Path(row[column]).resolve() in blocked:
                raise ValueError("superseded file referenced by current catalogue")
        path = Path(row[2]).resolve()
        if not path.is_relative_to(root) or digest(path) != row[10]:
            raise ValueError("current catalogue media integrity mismatch")
        if row[15] != "Нет":
            raise ValueError("current catalogue admits training")
    overrides = {item["page_id"]: item for item in replacement["replacements"]}
    count, ocr_count = 0, 0
    for book in raw["books"]:
        page_records = [
            json.loads(line)
            for line in (root / book["directory"] / "pages.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        if len(page_records) != book["pdf_pages"]:
            raise ValueError("book page count mismatch")
        if {p["pdf_page"] for p in page_records} != set(
            range(1, book["pdf_pages"] + 1)
        ):
            raise ValueError("duplicate or missing book page numbers")
        for page in page_records:
            record_path = (
                root / book["directory"] / "records" / f"{page['pdf_page']:04d}.json"
            )
            if page["page_id"] in overrides:
                record_path = root / overrides[page["page_id"]]["corrected_record"]
                if (
                    digest(record_path)
                    != overrides[page["page_id"]]["corrected_record_sha256"]
                ):
                    raise ValueError("corrected page record hash mismatch")
                page = json.loads(record_path.read_text(encoding="utf-8"))
            image_path = (root / page["page_preview"]["path"]).resolve()
            if assets.get(image_path) != page["page_preview"]["sha256"]:
                raise ValueError("effective page not in current assets")
            if (
                page["original_sha256"] != book["original_sha256"]
                or page["training_admitted"] is not False
            ):
                raise ValueError("effective page source/admission mismatch")
            if (
                assets.get((root / page["text_file"]["path"]).resolve())
                != page["text_file"]["sha256"]
            ):
                raise ValueError("effective text file missing from current assets")
            for image in page["images"]:
                if (
                    assets.get((root / image["media"]["path"]).resolve())
                    != image["media"]["sha256"]
                ):
                    raise ValueError("effective crop absent from current assets")
            ocr_path = record_path.parent.parent / "ocr" / record_path.name
            ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
            if (
                ocr["page_id"] != page["page_id"]
                or ocr["image_sha256"] != page["page_preview"]["sha256"]
                or Path(ocr["image"]).resolve() != image_path
                or ocr["training_admitted"] is not False
                or ocr["original_sha256"] != book["original_sha256"]
            ):
                raise ValueError("effective OCR is not bound to effective page")
            if ocr_path.resolve() not in assets:
                raise ValueError("effective OCR missing from current raw assets")
            count += 1
            ocr_count += 1
    if (
        count != 1763
        or ocr_count != 1763
        or merged["stats"]["effective_pages"] != count
        or merged["stats"]["ocr_pages"] != ocr_count
    ):
        raise ValueError("expected complete 1763-page corpus")
    if (
        merged["training_started"] is not False
        or merged["training_admitted"] is not False
    ):
        raise ValueError("training boundary violated")
    return {
        "status": "INDEPENDENT_HASH_CONFINEMENT_EFFECTIVE_PAGE_OCR_AND_SUPERSEDED_EXCLUSION_VERIFIED",
        "merge_sha256": digest(merge_path),
        "raw_assets_checked": len(merged["raw_assets"]),
        "media_rows_checked": len(merged["media"]),
        "effective_pages": count,
        "effective_ocr_pages": ocr_count,
        "superseded_files_excluded": len(blocked),
        "training_admitted": False,
        "limit": "integrity and coverage only, not semantic/OCR accuracy or training admission",
    }


class PartsReader(io.RawIOBase):
    """Seekable ZIP byte-stream backed by verified parts, without a second copy."""

    def __init__(self, paths: list[Path]):
        self.paths = paths
        self.sizes = [p.stat().st_size for p in paths]
        self.length = sum(self.sizes)
        self.position = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = (
            offset
            if whence == 0
            else self.position + offset
            if whence == 1
            else self.length + offset
        )
        if position < 0 or whence not in (0, 1, 2):
            raise ValueError("invalid seek")
        self.position = position
        return position

    def read(self, size=-1):
        remaining = (
            max(0, self.length - self.position)
            if size < 0
            else min(size, max(0, self.length - self.position))
        )
        result = bytearray()
        start = 0
        for path, length in zip(self.paths, self.sizes, strict=True):
            if start <= self.position < start + length and remaining:
                local = self.position - start
                take = min(remaining, length - local)
                with path.open("rb") as stream:
                    stream.seek(local)
                    chunk = stream.read(take)
                if len(chunk) != take:
                    raise ValueError("part changed during reading")
                result.extend(chunk)
                self.position += take
                remaining -= take
            start += length
        return bytes(result)


def verify_parts(parts_manifest_path: Path) -> tuple[dict, dict, list[Path]]:
    metadata = json.loads(parts_manifest_path.read_text(encoding="utf-8"))
    inventory_path = parts_manifest_path.parent / safe_name(metadata["input_manifest"])
    if digest(inventory_path) != metadata["input_manifest_sha256"]:
        raise ValueError("input manifest hash mismatch")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    combined, paths = hashlib.sha256(), []
    for part in metadata["parts"]:
        name = safe_name(part["path"])
        path = (parts_manifest_path.parent / name).resolve()
        if (
            not path.is_relative_to(parts_manifest_path.parent.resolve())
            or path.is_symlink()
            or path.stat().st_size != part["bytes"]
            or not 0 < part["bytes"] <= MAX_PART_BYTES
            or digest(path) != part["sha256"]
        ):
            raise ValueError("part integrity or confinement mismatch")
        paths.append(path)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(CHUNK), b""):
                combined.update(chunk)
    if (
        combined.hexdigest() != metadata["zip_sha256"]
        or sum(p.stat().st_size for p in paths) != metadata["zip_bytes"]
    ):
        raise ValueError("reconstructed ZIP byte-stream mismatch")
    return metadata, inventory, paths


def verify_zip(reader, inventory: dict, destination: Path | None = None) -> dict:
    files = {safe_name(item["path"]): item for item in inventory["files"]}
    directories = {safe_name(name) for name in inventory["directories"]}
    expected = set(files) | {name + "/" for name in directories}
    if len(files) != len(inventory["files"]) or len(directories) != len(
        inventory["directories"]
    ):
        raise ValueError("duplicate inventory paths")
    total = 0
    with zipfile.ZipFile(reader) as archive:
        names = archive.namelist()
        if set(names) != expected or len(names) != len(expected):
            raise ValueError("ZIP inventory mismatch or duplicate members")
        collisions = set()
        for info in archive.infolist():
            normalized = safe_name(info.filename)
            key = unicodedata.normalize("NFC", normalized).casefold()
            if key in collisions:
                raise ValueError("case/Unicode path collision")
            collisions.add(key)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if kind not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG):
                raise ValueError("symlink or special archive member")
            if info.is_dir() and info.file_size != 0:
                raise ValueError("directory carries data")
            if not info.is_dir() and info.file_size != files[normalized]["bytes"]:
                raise ValueError("ZIP entry size mismatch")
        for filename in files:
            if any(
                parent.as_posix() in files
                for parent in PurePosixPath(filename).parents
                if str(parent) != "."
            ):
                raise ValueError("file/parent path collision")
        if destination is not None:
            if destination.is_symlink() or (
                destination.exists()
                and getattr(destination.lstat(), "st_file_attributes", 0) & 0x400
            ):
                raise ValueError(
                    "restore destination cannot be a symlink or reparse point"
                )
            destination = destination.resolve()
            if destination.exists() and (
                not destination.is_dir() or any(destination.iterdir())
            ):
                raise ValueError("restore destination must be a new or empty directory")
            destination.mkdir(parents=True, exist_ok=True)
            for name in sorted(directories):
                target = destination / name
                if not target.resolve().is_relative_to(destination):
                    raise ValueError("restore directory escapes destination")
                target.mkdir(parents=True, exist_ok=True)
        for name, item in files.items():
            value = hashlib.sha256()
            count = 0
            target_stream = None
            if destination is not None:
                target = destination / name
                if not target.resolve().is_relative_to(destination):
                    raise ValueError("restore file escapes destination")
                target.parent.mkdir(parents=True, exist_ok=True)
                target_stream = target.open("xb")
            try:
                with archive.open(name) as source:
                    for chunk in iter(lambda: source.read(CHUNK), b""):
                        value.update(chunk)
                        count += len(chunk)
                        if count > item["bytes"]:
                            raise ValueError("entry exceeds declared size")
                        if target_stream:
                            target_stream.write(chunk)
            finally:
                if target_stream:
                    target_stream.close()
            if count != item["bytes"] or value.hexdigest() != item["sha256"]:
                raise ValueError(f"ZIP member SHA mismatch: {name}")
            if destination is not None:
                os.utime(destination / name, ns=(item["mtime_ns"], item["mtime_ns"]))
            total += count
    if total != inventory["total_bytes"]:
        raise ValueError("restored total bytes mismatch")
    return {
        "files_verified": len(files),
        "total_bytes_verified": total,
        "restored": destination is not None,
    }


def create(root: Path, output: Path, merge: Path | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root) or root.is_relative_to(output) or output.exists():
        raise ValueError("archive output must be fresh and outside corpus")
    if not root.is_dir():
        raise ValueError("corpus root missing")
    merge_audit = audit_merge(merge, root) if merge is not None else None
    files, directories = collect(root)
    superseded_paths = set()
    effective_report = root / "effective-coverage-report.json"
    if effective_report.exists():
        for row in json.loads(effective_report.read_text(encoding="utf-8"))[
            "superseded_unusable_media"
        ]:
            superseded_paths.add(row["page_preview"]["path"])
            superseded_paths.update(image["path"] for image in row["images"])
    corrections = root / "geometry-corrections/replacement-index.json"
    if corrections.exists():
        for row in json.loads(corrections.read_text(encoding="utf-8"))["replacements"]:
            superseded_paths.add(row["superseded_record"])
            superseded_paths.add(row["superseded_record"].replace("/records/", "/ocr/"))
    for item in files:
        item["role"] = (
            "ARCHIVE_ONLY_SUPERSEDED"
            if item["path"] in superseded_paths
            else "CORPUS_DRAFT_ASSET_OR_PROVENANCE"
        )
    inventory = {
        "schema": 1,
        "source_root": str(root),
        "training_admitted": False,
        "exclusions": [],
        "files": files,
        "directories": directories,
        "total_bytes": sum(item["bytes"] for item in files),
        "superseded_archive_only_files": sum(
            item["role"] == "ARCHIVE_ONLY_SUPERSEDED" for item in files
        ),
        "limits": "all bytes preserved, including superseded resources; restore does not grant training admission; effective views must use correction overrides",
    }
    output.mkdir(parents=True)
    inventory_path = output / "input-manifest.json"
    save(inventory_path, inventory)
    if merge_audit:
        save(output / "merge-integrity-audit.json", merge_audit)
    zip_path = output / "corpus.zip"
    with zipfile.ZipFile(
        zip_path,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for name in directories:
            info = zipfile.ZipInfo(name + "/", (1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(info, b"")
        for item in files:
            info = zipfile.ZipInfo(item["path"], (1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            value = hashlib.sha256()
            with (
                (root / item["path"]).open("rb") as source,
                archive.open(info, "w", force_zip64=True) as target,
            ):
                for chunk in iter(lambda: source.read(CHUNK), b""):
                    value.update(chunk)
                    target.write(chunk)
            if value.hexdigest() != item["sha256"]:
                raise ValueError("source changed while archiving")
    initial_verification = verify_zip(zip_path, inventory)
    parts = []
    with zip_path.open("rb") as source:
        index = 1
        while True:
            data = source.read(MAX_PART_BYTES)
            if not data:
                break
            name = f"corpus.zip.part{index:04d}"
            with (output / name).open("xb") as target:
                target.write(data)
            parts.append(
                {
                    "path": name,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            index += 1
    metadata = {
        "schema": 1,
        "format": "CONCATENATED_ZIP_PARTS_NOT_MULTIVOLUME_ZIP",
        "input_manifest": inventory_path.name,
        "input_manifest_sha256": digest(inventory_path),
        "zip_sha256": digest(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "max_part_bytes": MAX_PART_BYTES,
        "parts": parts,
        "training_admitted": False,
    }
    parts_path = output / "parts-manifest.json"
    save(parts_path, metadata)
    _, reconstructed_inventory, paths = verify_parts(parts_path)
    with PartsReader(paths) as reader:
        reconstructed_verification = verify_zip(reader, reconstructed_inventory)
    final_files, final_directories = collect(root)
    if final_directories != directories or [
        (i["path"], i["sha256"], i["bytes"], i["mtime_ns"]) for i in final_files
    ] != [(i["path"], i["sha256"], i["bytes"], i["mtime_ns"]) for i in files]:
        raise ValueError("source corpus changed during archival")
    receipt = {
        "status": "COMPLETE_SOURCE_PRESERVING_ZIP_AND_RECONSTRUCTED_PART_STREAM_VERIFIED",
        "source_files": len(files),
        "source_bytes": inventory["total_bytes"],
        "zip_bytes": metadata["zip_bytes"],
        "zip_sha256": metadata["zip_sha256"],
        "parts": len(parts),
        "max_part_bytes": MAX_PART_BYTES,
        "input_manifest_sha256": metadata["input_manifest_sha256"],
        "parts_manifest_sha256": digest(parts_path),
        "whole_zip_verification": initial_verification,
        "reconstructed_stream_verification": reconstructed_verification,
        "source_before_after_identity_verified": True,
        "source_deleted_or_modified": False,
        "exclusions": [],
        "training_started": False,
        "merge_audit": merge_audit,
        "limits": "integrity/coverage only; OCR and semantic labels remain draft; originals outside corpus require their separate existing backup",
    }
    save(output / "archive-receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--merge", type=Path)
    parser.add_argument("--restore", type=Path, metavar="PARTS_MANIFEST")
    parser.add_argument("--destination", type=Path)
    arguments = parser.parse_args()
    if arguments.restore:
        if not arguments.destination:
            parser.error("--restore requires --destination")
        metadata, inventory, parts = verify_parts(arguments.restore.resolve())
        with PartsReader(parts) as stream:
            result = verify_zip(stream, inventory, arguments.destination)
        print(
            json.dumps(
                {"status": "RESTORE_FILES_SHA_AND_TOTAL_BYTES_VERIFIED", **result},
                ensure_ascii=True,
            )
        )
    else:
        if not arguments.root or not arguments.output:
            parser.error("archive requires --root and --output")
        print(
            json.dumps(
                create(arguments.root, arguments.output, arguments.merge),
                ensure_ascii=True,
            )
        )

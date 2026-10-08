"""Inventory unchanged user-supplied PDFs. Does not approve rights or training.

Text/image-resource presence is not a layout/comprehension quality certificate.
Only manifest metadata is written; source PDFs are never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExtractionWarnings(logging.Handler):
    """Retain bounded diagnostics without dumping font dictionaries."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.page: int | None = None
        self.count = 0
        self.pages: set[int] = set()
        self.samples: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1
        if self.page is not None:
            self.pages.add(self.page)
        message = record.getMessage()[:240]
        if message not in self.samples and len(self.samples) < 8:
            self.samples.append(message)


def inspect_pdf(path: Path) -> dict:
    logger = logging.getLogger("pypdf")
    capture = ExtractionWarnings()
    prior_propagate = logger.propagate
    logger.addHandler(capture)
    logger.propagate = False
    try:
        return _inspect_pdf(path, capture)
    finally:
        logger.removeHandler(capture)
        logger.propagate = prior_propagate


def _inspect_pdf(path: Path, capture: ExtractionWarnings) -> dict:
    before = file_sha256(path)
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError(f"encrypted PDF requires explicit handling: {path.name}")
    text_counts, sizes, direct_images = [], set(), []
    for number, page in enumerate(reader.pages, 1):
        capture.page = number
        text_counts.append(len((page.extract_text() or "").strip()))
        sizes.add(
            (
                round(float(page.mediabox.width), 3),
                round(float(page.mediabox.height), 3),
            )
        )
        resources = page.get("/Resources")
        resources = resources.get_object() if resources else {}
        objects = resources.get("/XObject")
        objects = objects.get_object() if objects else {}
        direct_images.append(
            sum(
                obj.get_object().get("/Subtype") == "/Image" for obj in objects.values()
            )
        )
    if before != file_sha256(path):
        raise ValueError(f"source changed during inventory: {path.name}")
    metadata = reader.metadata or {}
    return {
        "source_id": "sha256:" + before,
        "path": "originals/" + path.name,
        "original_filename": path.name,
        "sha256": before,
        "bytes": path.stat().st_size,
        "pages": len(reader.pages),
        "pdf_metadata_title": str(metadata.get("/Title", "")),
        "pdf_metadata_author": str(metadata.get("/Author", "")),
        "page_sizes_points": [list(s) for s in sorted(sizes)],
        "text_layer": {
            "pages_with_text": sum(n > 0 for n in text_counts),
            "chars_by_pdf_page": text_counts,
            "quality_status": "PARSER_WARNINGS_REVIEW_REQUIRED"
            if capture.count
            else "PRESENCE_ONLY_NOT_SEMANTICALLY_VALIDATED",
            "parser_warning_count": capture.count,
            "pdf_pages_with_parser_warnings": sorted(capture.pages),
            "parser_warning_samples": capture.samples,
            "note": "presence only; warnings can mean incomplete extraction; not OCR accuracy, reading order or complete visual semantics",
        },
        "direct_image_xobjects_by_pdf_page": direct_images,
        "image_count_note": "PDF resource objects only; nested forms/vector drawings omitted; NOT depicted object counts",
        "rights_status": "UNREVIEWED_USER_SUPPLIED_NOT_PUBLIC_RELEASE_APPROVED",
        "training_status": "NOT_ADMITTED",
        "split_group": "UNASSIGNED_PENDING_WORK_EDITION_AND_DUPLICATE_IMAGE_REVIEW",
    }


def build_manifest(directory: Path) -> dict:
    paths = sorted(directory.glob("*.pdf"), key=lambda p: p.name.casefold())
    if not paths:
        raise ValueError("no PDF originals found")
    books = [inspect_pdf(p) for p in paths]
    if len({book["sha256"] for book in books}) != len(books):
        raise ValueError("byte-identical duplicate originals; review before admission")
    return {
        "schema": 2,
        "corpus_id": "belarus-primary-user-supplied-20261008",
        "scope": "Russian-language Belarus grades 1-2 originals supplied by user",
        "original_bytes_modified": False,
        "public_pdf_release_approved": False,
        "training_admitted": False,
        "total_files": len(books),
        "total_bytes": sum(b["bytes"] for b in books),
        "total_pdf_pages": sum(b["pages"] for b in books),
        "books": books,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refuse overwriting existing inventory")
    manifest = build_manifest(args.originals.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {k: v for k, v in manifest.items() if k != "books"}, ensure_ascii=False
        )
    )
    for book in manifest["books"]:
        print(
            json.dumps(
                {
                    k: book[k]
                    for k in (
                        "original_filename",
                        "sha256",
                        "bytes",
                        "pages",
                        "pdf_metadata_title",
                        "pdf_metadata_author",
                    )
                },
                ensure_ascii=False,
            )
        )

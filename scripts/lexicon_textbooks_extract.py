"""Preserve PDF pages, text layers and raster-placement crops; never train.

All page scenes are kept because PDF image resources are not depicted objects
and vector artwork cannot be exhaustively segmented by this extractor. Text is
unreviewed parser output, not verified OCR or illustration-word alignment.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import math
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encoded_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def preserve(path: Path, data: bytes) -> None:
    """Resume only byte-identical outputs; never overwrite existing user files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"existing output differs: {path}")
        return
    with path.open("xb") as stream:
        stream.write(data)


def family(filename: str) -> str:
    stem = Path(filename).stem.casefold()
    if "matematika" in stem:
        return "matematika-muravyova-primary"
    if "lit_chtenie" in stem:
        return "literaturnoe-chtenie-voropaeva-grade2"
    if "rus_yaz" in stem:
        return "russkiy-yazyk-guleckaya-grade2"
    if "chel_i_mir" in stem:
        return "chelovek-i-mir-trafimova-primary"
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "unknown-primary-family"


def pixel_bbox(
    bbox: list[float], width: float, height: float, pixels: tuple[int, int]
) -> tuple[int, int, int, int]:
    x0, top, x1, bottom = bbox
    if (
        not all(math.isfinite(v) for v in (*bbox, width, height))
        or width <= 0
        or height <= 0
    ):
        raise ValueError("invalid page or placement coordinates")
    left = max(0, min(pixels[0], math.floor(x0 / width * pixels[0])))
    upper = max(0, min(pixels[1], math.floor(top / height * pixels[1])))
    right = max(0, min(pixels[0], math.ceil(x1 / width * pixels[0])))
    lower = max(0, min(pixels[1], math.ceil(bottom / height * pixels[1])))
    if right <= left or lower <= upper:
        raise ValueError("placement outside page or zero area")
    return left, upper, right, lower


def asset(path: Path, root: Path, data: bytes) -> dict:
    preserve(path, data)
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "bytes": len(data),
    }


def image_bytes(image, quality: int = 88) -> bytes:
    stream = io.BytesIO()
    image.convert("RGB").save(
        stream, format="JPEG", quality=quality, optimize=True, subsampling=0
    )
    return stream.getvalue()


def verify_record(record: dict, root: Path, source_hash: str) -> None:
    if (
        record["original_sha256"] != source_hash
        or record["training_admitted"] is not False
    ):
        raise ValueError("record source/admission mismatch")
    records = [
        record["page_preview"],
        record["text_file"],
        *[r["media"] for r in record["images"]],
    ]
    for item in records:
        target = (root / item["path"]).resolve()
        if (
            not target.is_relative_to(root.resolve())
            or not target.is_file()
            or sha256(target) != item["sha256"]
        ):
            raise ValueError(f"record asset missing or altered: {item['path']}")


class Warnings(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.samples: list[str] = []
        self.count = 0

    def emit(self, record):
        self.count += 1
        if len(self.samples) < 8:
            self.samples.append(record.getMessage()[:240])


def extract_page(
    page,
    renderer,
    book: dict,
    number: int,
    root: Path,
    dpi: int,
    prefix_base: str = "books",
) -> dict:
    prefix = Path(prefix_base) / book["sha256"][:16]
    identifier = f"{book['sha256'][:16]}-p{number:04d}"
    common = {
        "original_sha256": book["sha256"],
        "original_filename": book["original_filename"],
        "source_id": book["source_id"],
        "family_id": family(book["original_filename"]),
        "pdf_page": number,
        "split": "UNASSIGNED",
        "training_admitted": False,
        "bbox_coordinate_system": "PDF_POINTS_TOP_LEFT_X0_TOP_X1_BOTTOM",
    }
    rendered_page = renderer[number - 1]
    original_cropbox = rendered_page.get_cropbox()
    media_box = rendered_page.get_mediabox()
    # Render the full MediaBox used by pdfplumber. A narrower CropBox (common
    # for covers split across two PDF pages) otherwise misaligns placements.
    # This changes only the in-memory PDFium page, never the source PDF bytes.
    rendered_page.set_cropbox(*media_box)
    bitmap = rendered_page.render(scale=dpi / 72)
    try:
        image = bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()
        rendered_page.close()
    preview = asset(
        root / prefix / "pages" / f"{number:04d}.jpg", root, image_bytes(image)
    )
    handler = Warnings()
    log = logging.getLogger("pdfminer")
    prior_propagate = log.propagate
    log.addHandler(handler)
    log.propagate = False
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
        text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
        placements = page.images
        vector_count = len(page.curves) + len(page.rects) + len(page.lines)
    finally:
        log.removeHandler(handler)
        log.propagate = prior_propagate
    text_asset = asset(
        root / prefix / "text" / f"{number:04d}.txt",
        root,
        (text + "\n").encode("utf-8"),
    )
    images, rejected = [], []
    for index, placement in enumerate(placements, 1):
        bbox = [float(placement[k]) for k in ("x0", "top", "x1", "bottom")]
        try:
            origin_x, origin_top = page.bbox[:2]
            relative_bbox = [
                bbox[0] - origin_x,
                bbox[1] - origin_top,
                bbox[2] - origin_x,
                bbox[3] - origin_top,
            ]
            pixels = pixel_bbox(relative_bbox, page.width, page.height, image.size)
        except ValueError as error:
            rejected.append({"placement": index, "bbox": bbox, "reason": str(error)})
            continue
        crop = image.crop(pixels)
        try:
            media = asset(
                root / prefix / "placements" / f"{number:04d}-{index:04d}.jpg",
                root,
                image_bytes(crop),
            )
        finally:
            crop.close()
        images.append(
            {
                **common,
                "media_id": f"{identifier}-r{index:04d}"
                + ("-geometry-v2" if prefix_base == "geometry-corrections" else ""),
                "kind": "RASTER_PLACEMENT_COMPOSITED_CROP",
                "bbox": bbox,
                "crop_pixel_bbox": list(pixels),
                "media": media,
                "page_preview": preview["path"],
                "resource_name": str(placement.get("name", "")),
                "resource_imagemask": bool(placement.get("imagemask", False)),
                "label_status": "UNREVIEWED_NOT_OBJECT_SEGMENTATION",
                "concept_ids": [],
            }
        )
    result = {
        **common,
        "page_id": identifier,
        "page_size_points": [page.width, page.height],
        "render_dpi": dpi,
        "render_box_policy": "FULL_MEDIABOX_MATCHING_TEXT_COORDINATES",
        "original_cropbox_bottom_left": list(original_cropbox),
        "rendered_mediabox_bottom_left": list(media_box),
        "pixel_size": list(image.size),
        "page_preview": preview,
        "text_file": text_asset,
        "text": text,
        "words": [
            {"text": w["text"], "bbox": [w[k] for k in ("x0", "top", "x1", "bottom")]}
            for w in words
        ],
        "text_status": "TEXT_LAYER_REQUIRES_VISUAL_OCR_REVIEW"
        if text.strip()
        else "NO_TEXT_LAYER_OCR_REQUIRED",
        "text_replacement_character_count": text.count("\ufffd"),
        "parser_warning_count": handler.count,
        "parser_warning_samples": handler.samples,
        "raster_placement_count": len(placements),
        "vector_primitive_count": vector_count,
        "images": images,
        "rejected_placements": rejected,
        "illustration_coverage": "FULL_PAGE_CONTEXT_PRESERVED_VECTOR_AND_OBJECT_SEGMENTATION_UNREVIEWED",
    }
    image.close()
    return result


def extract_book(book: dict, source: Path, root: Path, dpi: int) -> dict:
    if sha256(source) != book["sha256"] or source.stat().st_size != book["bytes"]:
        raise ValueError(f"original does not match manifest: {source.name}")
    import pdfplumber
    import pypdfium2

    directory = root / "books" / book["sha256"][:16]
    preserve(directory / "source.json", encoded_json(book))
    records = []
    renderer = pypdfium2.PdfDocument(source)
    try:
        with pdfplumber.open(source) as document:
            if len(document.pages) != book["pages"] or len(renderer) != book["pages"]:
                raise ValueError("page count differs from original manifest")
            for number, page in enumerate(document.pages, 1):
                record_path = directory / "records" / f"{number:04d}.json"
                if record_path.exists():
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    if record["render_dpi"] != dpi or record["pdf_page"] != number:
                        raise ValueError("existing record configuration differs")
                    verify_record(record, root, book["sha256"])
                else:
                    record = extract_page(page, renderer, book, number, root, dpi)
                    preserve(record_path, encoded_json(record))
                records.append(record)
                page.close()
                if number == 1 or number % 40 == 0:
                    print(
                        json.dumps(
                            {
                                "book": source.name,
                                "page": number,
                                "pages": book["pages"],
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
    finally:
        renderer.close()
    if sha256(source) != book["sha256"]:
        raise ValueError("source changed during extraction")
    preserve(
        directory / "pages.jsonl",
        b"".join(
            (json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            for r in records
        ),
    )
    preserve(
        directory / "images.jsonl",
        b"".join(
            (json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            for p in records
            for r in p["images"]
        ),
    )
    return {
        "original_filename": source.name,
        "original_sha256": book["sha256"],
        "family_id": family(source.name),
        "directory": directory.relative_to(root).as_posix(),
        "pdf_pages": len(records),
        "pages_with_text": sum(bool(p["text"].strip()) for p in records),
        "words": sum(len(p["words"]) for p in records),
        "raster_placements": sum(p["raster_placement_count"] for p in records),
        "preserved_crops": sum(len(p["images"]) for p in records),
        "rejected_placements": sum(len(p["rejected_placements"]) for p in records),
        "ocr_review_pages": [
            p["pdf_page"]
            for p in records
            if not p["text"].strip()
            or p["text_replacement_character_count"]
            or p["parser_warning_count"]
        ],
        "original_verified_before_and_after": True,
    }


def run(
    manifest_path: Path, root: Path, dpi: int = 110, book_names: list[str] | None = None
) -> dict:
    if not 72 <= dpi <= 200:
        raise ValueError("DPI outside bounded preservation range 72..200")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = [
        b
        for b in manifest["books"]
        if not book_names or b["original_filename"] in book_names
    ]
    if not selected or (
        book_names and set(book_names) != {b["original_filename"] for b in selected}
    ):
        raise ValueError("requested book missing from manifest")
    root = root.resolve()
    config = {
        "schema": 1,
        "manifest_sha256": sha256(manifest_path),
        "dpi": dpi,
        "training_admitted": False,
        "ocr_performed": False,
        "text_verified": False,
        "originals_unchanged": True,
        "crop_kind": "COMPOSITED_PAGE_RASTER_PLACEMENTS_NOT_OBJECTS",
    }
    preserve(root / "extraction-config.json", encoded_json(config))
    books, failures = [], []
    for book in selected:
        source = (manifest_path.parent / book["path"]).resolve()
        if not source.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError("source path escapes original corpus directory")
        try:
            books.append(extract_book(book, source, root, dpi))
        except Exception as error:  # noqa: BLE001 - preserve per-book failure evidence, exit nonzero.
            failures.append(
                {
                    "book": book["original_filename"],
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            print(json.dumps(failures[-1], ensure_ascii=True), flush=True)
    report = {
        **config,
        "books": books,
        "failures": failures,
        "total_pages": sum(b["pdf_pages"] for b in books),
        "total_crops": sum(b["preserved_crops"] for b in books),
        "status": "EXTRACTION_PRESERVED_PENDING_TEXT_OCR_AND_VISUAL_LABEL_REVIEW"
        if not failures
        else "INCOMPLETE_FAILURES_REQUIRE_REVIEW",
    }
    suffix = (
        "-"
        + hashlib.sha256("|".join(b["sha256"] for b in selected).encode()).hexdigest()[
            :12
        ]
        if book_names
        else ""
    )
    preserve(root / f"report{suffix}.json", encoded_json(report))
    return report


def contact_sheets(root: Path) -> list[dict]:
    """Review aids only: retain page numbers, never create object labels."""
    from PIL import Image, ImageDraw

    result = []
    replacements_path = root / "geometry-corrections" / "replacement-index.json"
    replacements = (
        json.loads(replacements_path.read_text(encoding="utf-8"))["replacements"]
        if replacements_path.exists()
        else []
    )
    overrides = {item["page_id"]: item["corrected_record"] for item in replacements}
    for directory in sorted((root / "books").iterdir()):
        index = directory / "pages.jsonl"
        if not index.is_file():
            continue
        records = [
            json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()
        ]
        records = [
            json.loads((root / overrides[r["page_id"]]).read_text(encoding="utf-8"))
            if r["page_id"] in overrides
            else r
            for r in records
        ]
        for offset in range(0, len(records), 12):
            subset = records[offset : offset + 12]
            sheet = Image.new("RGB", (990, 1900), "white")
            draw = ImageDraw.Draw(sheet)
            for position, record in enumerate(subset):
                verify_record(record, root, record["original_sha256"])
                column, row = position % 3, position // 3
                with Image.open(root / record["page_preview"]["path"]) as image:
                    image.thumbnail((320, 445))
                    sheet.paste(image, (column * 330 + 5, row * 475 + 25))
                draw.text(
                    (column * 330 + 5, row * 475 + 5),
                    f"PDF page {record['pdf_page']} / crops {len(record['images'])}",
                    fill="black",
                )
            path = (
                directory
                / "contact-sheets"
                / f"{offset + 1:04d}-{offset + len(subset):04d}.jpg"
            )
            result.append(
                {
                    "original_sha256": records[0]["original_sha256"],
                    "pdf_pages": [p["pdf_page"] for p in subset],
                    "media": asset(path, root, image_bytes(sheet)),
                }
            )
            sheet.close()
    preserve(root / "contact-sheets.json", encoded_json(result))
    return result


def correct_geometry(manifest_path: Path, root: Path, dpi: int) -> dict:
    """Non-destructive overrides for legacy extraction's CropBox/MediaBox mismatch."""
    import pdfplumber
    import pypdfium2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replacements = []
    for book in manifest["books"]:
        source = (manifest_path.parent / book["path"]).resolve()
        if not source.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError("source path escapes original corpus directory")
        if sha256(source) != book["sha256"]:
            raise ValueError("original hash mismatch before geometry audit")
        renderer = pypdfium2.PdfDocument(source)
        try:
            with pdfplumber.open(source) as document:
                for number, page in enumerate(document.pages, 1):
                    if tuple(page.cropbox) == tuple(page.mediabox):
                        page.close()
                        continue
                    path = (
                        root
                        / "geometry-corrections"
                        / book["sha256"][:16]
                        / "records"
                        / f"{number:04d}.json"
                    )
                    if path.exists():
                        record = json.loads(path.read_text(encoding="utf-8"))
                        if (
                            record["render_dpi"] != dpi
                            or record.get("render_box_policy")
                            != "FULL_MEDIABOX_MATCHING_TEXT_COORDINATES"
                        ):
                            raise ValueError(
                                "existing correction configuration differs"
                            )
                        verify_record(record, root, book["sha256"])
                    else:
                        record = extract_page(
                            page,
                            renderer,
                            book,
                            number,
                            root,
                            dpi,
                            "geometry-corrections",
                        )
                        preserve(path, encoded_json(record))
                    previous_path = (
                        root
                        / "books"
                        / book["sha256"][:16]
                        / "records"
                        / f"{number:04d}.json"
                    )
                    previous = (
                        json.loads(previous_path.read_text(encoding="utf-8"))
                        if previous_path.exists()
                        else {}
                    )
                    replacements.append(
                        {
                            "page_id": record["page_id"],
                            "original_sha256": book["sha256"],
                            "pdf_page": number,
                            "corrected_record": path.relative_to(root).as_posix(),
                            "corrected_record_sha256": sha256(path),
                            "superseded_media": [
                                {"media_id": item["media_id"], **item["media"]}
                                for item in previous.get("images", [])
                            ],
                            "superseded_page_preview": previous.get("page_preview"),
                            "superseded_record": f"books/{book['sha256'][:16]}/records/{number:04d}.json",
                            "reason": "LEGACY_CROPBOX_RENDER_DID_NOT_MATCH_MEDIABOX_TEXT_COORDINATES",
                            "training_admitted": False,
                        }
                    )
                    page.close()
        finally:
            renderer.close()
        if sha256(source) != book["sha256"]:
            raise ValueError("original changed during geometry audit")
    result = {
        "schema": 1,
        "manifest_sha256": sha256(manifest_path),
        "training_admitted": False,
        "originals_verified_before_after": True,
        "replacements": replacements,
        "rule": "Merge by page_id, replace entire page/images records; preserve superseded files but do not admit them.",
    }
    preserve(
        root / "geometry-corrections" / "replacement-index.json", encoded_json(result)
    )
    return result


def effective_coverage(root: Path) -> dict:
    """Verify immutable originals' extraction plus geometry overrides separately."""
    raw_report_path = root / "report.json"
    raw = json.loads(raw_report_path.read_text(encoding="utf-8"))
    correction_path = root / "geometry-corrections" / "replacement-index.json"
    corrections = json.loads(correction_path.read_text(encoding="utf-8"))
    if raw["manifest_sha256"] != corrections["manifest_sha256"]:
        raise ValueError("geometry audit used a different original manifest")
    overrides = {item["page_id"]: item for item in corrections["replacements"]}
    books, superseded = [], []
    for book in raw["books"]:
        records = [
            json.loads(line)
            for line in (root / book["directory"] / "pages.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        effective = []
        for record in records:
            if record["page_id"] in overrides:
                superseded.append(
                    {
                        "page_id": record["page_id"],
                        "page_preview": record["page_preview"],
                        "images": [
                            {"media_id": item["media_id"], **item["media"]}
                            for item in record["images"]
                        ],
                    }
                )
                replacement = overrides[record["page_id"]]
                corrected_path = root / replacement["corrected_record"]
                if sha256(corrected_path) != replacement["corrected_record_sha256"]:
                    raise ValueError("corrected record changed")
                record = json.loads(corrected_path.read_text(encoding="utf-8"))
            verify_record(record, root, book["original_sha256"])
            effective.append(record)
        books.append(
            {
                "original_filename": book["original_filename"],
                "original_sha256": book["original_sha256"],
                "pdf_pages": len(effective),
                "words": sum(len(p["words"]) for p in effective),
                "crops": sum(len(p["images"]) for p in effective),
                "rejected_placements": sum(
                    len(p["rejected_placements"]) for p in effective
                ),
            }
        )
    result = {
        "schema": 1,
        "training_admitted": False,
        "source_report_sha256": sha256(raw_report_path),
        "correction_index_sha256": sha256(correction_path),
        "geometry_corrected_pages": len(superseded),
        "superseded_unusable_media": superseded,
        "books": books,
        "total_pages": sum(b["pdf_pages"] for b in books),
        "total_words": sum(b["words"] for b in books),
        "total_crops": sum(b["crops"] for b in books),
        "all_effective_media_hashes_verified": True,
        "text_and_labels_status": "UNREVIEWED_EXTRACTED_DRAFT_NOT_TRAINING_GOLD",
        "raw_failures": raw["failures"],
    }
    preserve(root / "effective-coverage-report.json", encoded_json(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=110)
    parser.add_argument("--book", action="append")
    parser.add_argument("--contacts-only", action="store_true")
    parser.add_argument("--geometry-corrections-only", action="store_true")
    parser.add_argument("--effective-audit-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.effective_audit_only:
        audited = effective_coverage(arguments.output.resolve())
        print(
            json.dumps(
                {
                    k: v
                    for k, v in audited.items()
                    if k not in ("books", "superseded_unusable_media")
                }
            ),
            flush=True,
        )
        raise SystemExit(1 if audited["raw_failures"] else 0)
    if arguments.geometry_corrections_only:
        corrected = correct_geometry(
            arguments.manifest.resolve(), arguments.output.resolve(), arguments.dpi
        )
        print(
            json.dumps(
                {
                    "corrected_pages": len(corrected["replacements"]),
                    "training_admitted": False,
                }
            ),
            flush=True,
        )
        raise SystemExit(0)
    if arguments.contacts_only:
        sheets = contact_sheets(arguments.output.resolve())
        print(
            json.dumps({"contact_sheets": len(sheets), "training_admitted": False}),
            flush=True,
        )
        raise SystemExit(0)
    result = run(
        arguments.manifest.resolve(), arguments.output, arguments.dpi, arguments.book
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("books",)}, ensure_ascii=True
        ),
        flush=True,
    )
    raise SystemExit(1 if result["failures"] else 0)

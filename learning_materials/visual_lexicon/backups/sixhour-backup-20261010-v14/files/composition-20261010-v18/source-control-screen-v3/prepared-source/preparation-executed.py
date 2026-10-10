"""Hash-checked PDF-source control tensors, never edits originals or trains.

Extracts existing page pixels and applies explicit inference preprocessing;
does not regenerate, repaint or reinterpret source artwork. Pairings are
correlated and must never be presented as independent source samples.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ai_brain.training import primary_composition as c


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_gallery(crops):
    """Display every original ROI byte, without fixed-cell clipping/overlap."""
    columns = min(8, len(crops))
    cell_width = max(crop.width for crop in crops) + 8
    cell_height = max(crop.height for crop in crops) + 8
    sheet = Image.new(
        "RGB",
        (columns * cell_width, ((len(crops) + columns - 1) // columns) * cell_height),
        (230, 230, 230),
    )
    for i, crop in enumerate(crops):
        sheet.paste(
            crop, (i % columns * cell_width + 4, i // columns * cell_height + 4)
        )
    return sheet


def verified_page(source, originals, derived):
    if (
        type(source["pdf_page"]) is not int
        or source["pdf_page"] < 1
        or type(source["dpi"]) is not int
        or not 1 <= source["dpi"] <= 300
        or not isinstance(source["pixel_size"], (list, tuple))
        or len(source["pixel_size"]) != 2
        or any(type(x) is not int or not 1 <= x <= 8192 for x in source["pixel_size"])
    ):
        raise ValueError("Invalid bounded original PDF rendering metadata")
    pdf = (originals / source["pdf"]).resolve()
    preview = (derived / source["preview"]).resolve()
    if not pdf.is_relative_to(originals.resolve()) or not preview.is_relative_to(
        derived.resolve()
    ):
        raise ValueError("Source path escaped scoped material directories")
    if sha(pdf) != source["pdf_sha256"] or sha(preview) != source["preview_sha256"]:
        raise ValueError("Original PDF/page-preview bytes changed")
    import pypdfium2

    document = pypdfium2.PdfDocument(pdf)
    try:
        if source["pdf_page"] > len(document):
            raise ValueError("Source PDF page outside original document")
        page = document[source["pdf_page"] - 1]
        try:
            page.set_cropbox(*page.get_mediabox())
            bitmap = page.render(scale=source["dpi"] / 72)
            try:
                rendered = bitmap.to_pil().convert("RGB")
                stream = io.BytesIO()
                rendered.save(
                    stream, format="JPEG", quality=88, optimize=True, subsampling=0
                )
                rendered.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()
    if hashlib.sha256(stream.getvalue()).hexdigest() != source["preview_sha256"]:
        raise ValueError("Preview is not an exact fresh rendering of original PDF")
    with Image.open(preview) as image:
        if list(image.size) != source["pixel_size"]:
            raise ValueError("Source preview geometry differs")
        return image.convert("RGB")


def asset_crop(asset, page):
    box = asset["bbox_pixels"]
    if (
        len(box) != 4
        or any(type(x) is not int for x in box)
        or not (
            0 <= box[0] < box[2] <= page.width and 0 <= box[1] < box[3] <= page.height
        )
    ):
        raise ValueError("Invalid source crop coordinates")
    if type(asset["absent"]) is not bool or any(
        (asset[task] is None) != asset["absent"] for task in c.VALUES
    ):
        raise ValueError("Source visibility and attribute annotation differ")
    if not asset["absent"] and any(
        not isinstance(asset[task], str) or not asset[task].strip() for task in c.VALUES
    ):
        raise ValueError("Source attributes require explicit lexical meanings")
    return page.crop(box)


def prepare(manifest_path, originals, derived, output):
    if output.exists():
        raise ValueError("Fresh source-control tensor directory required")
    manifest = read(manifest_path)
    before = sha(manifest_path)
    executed_source = Path(__file__).read_bytes()
    source_hash = hashlib.sha256(executed_source).hexdigest()
    course_hash = sha(Path(c.__file__))
    if (
        manifest["schema"] != 1
        or manifest["training_admitted"]
        or manifest["evaluation"]["training_or_calibration"]
        or manifest["assembly"]
        != {
            "pairs": "all ordered pairs of different source assets",
            "canvas": [96, 96],
            "background_rgb": [255, 255, 255],
            "target_centers": [[24, 48], [72, 48]],
            "fit_box": [32, 32],
            "preserve_aspect_ratio": True,
            "interpolation": "Pillow LANCZOS",
            "random_augmentations": False,
        }
    ):
        raise ValueError("Registered no-fitting source preprocessing required")
    sources = {s["id"]: s for s in manifest["sources"]}
    if len(sources) != len(manifest["sources"]):
        raise ValueError("Duplicate source identity")
    pages = {
        identity: verified_page(source, originals, derived)
        for identity, source in sources.items()
    }
    assets = manifest["assets"]
    if not 2 <= len(assets) <= 100 or len({a["id"] for a in assets}) != len(assets):
        raise ValueError("Distinct bounded source assets required")
    crops = [asset_crop(asset, pages[asset["source"]]) for asset in assets]
    asset_records = []
    for asset, crop in zip(assets, crops, strict=True):
        asset_records.append(
            {
                **asset,
                "crop_rgb_sha256": hashlib.sha256(
                    np.asarray(crop).tobytes()
                ).hexdigest(),
                "crop_size": list(crop.size),
            }
        )
    pixels, questions, labels, indices, records, scenes = [], [], [], [], [], []
    for left in range(len(assets)):
        for right in range(len(assets)):
            if left == right:
                continue
            index = len(pixels)
            canvas = Image.new("RGB", (96, 96), (255, 255, 255))
            for side, selected in enumerate((left, right)):
                crop = crops[selected].copy()
                crop.thumbnail((32, 32), Image.Resampling.LANCZOS)
                canvas.paste(
                    crop, ((24, 72)[side] - crop.width // 2, 48 - crop.height // 2)
                )
                crop.close()
            image = np.asarray(canvas).copy()
            canvas.close()
            pixels.append(image)
            identity = f"real-source/{assets[left]['id']}+{assets[right]['id']}"
            scenes.append(
                {
                    "identity": identity,
                    "asset_ids": [assets[left]["id"], assets[right]["id"]],
                }
            )
            for side, selected in enumerate((left, right)):
                asset = assets[selected]
                for task in c.VALUES:
                    value = asset[task]
                    label = (
                        c.UNKNOWN
                        if asset["absent"] or value not in c.VALUES[task]
                        else c.ANSWERS.index(value)
                    )
                    query = c.question(task, side, index % 3)
                    records.append(
                        {
                            "scene_id": identity,
                            "image_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                            "task": task,
                            "side": side,
                            "question": query,
                            "answer": label,
                            "source_asset_id": asset["id"],
                        }
                    )
                    questions.append(c.encode_question(query))
                    labels.append(label)
                    indices.append(index)
    for source in sources.values():
        if (
            sha(originals / source["pdf"]) != source["pdf_sha256"]
            or sha(derived / source["preview"]) != source["preview_sha256"]
        ):
            raise ValueError("Source material changed during preprocessing")
    if sha(manifest_path) != before:
        raise ValueError("Source annotation manifest changed")
    if sha(Path(__file__)) != source_hash or sha(Path(c.__file__)) != course_hash:
        raise ValueError("Preprocessing implementation changed")
    output.mkdir(parents=True)
    (output / "preparation-executed.py").write_bytes(executed_source)
    (output / "source-annotations.json").write_bytes(manifest_path.read_bytes())
    (output / "preparation-freeze.json").write_text(
        json.dumps(
            {
                "annotation_manifest_sha256": before,
                "preparation_source_sha256": source_hash,
                "course_source_sha256": course_hash,
                "answers": list(c.ANSWERS),
                "training_or_calibration": False,
                "production_admitted": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    np.savez_compressed(
        output / "source-crops.npz",
        **{f"asset_{i:03d}": np.asarray(crop) for i, crop in enumerate(crops)},
    )
    np.savez_compressed(
        output / "dataset.npz",
        **{
            "source_" + k: np.asarray(v, dtype=np.uint8 if k == "pixels" else np.int64)
            for k, v in (
                ("pixels", pixels),
                ("questions", questions),
                ("labels", labels),
                ("image_index", indices),
            )
        },
    )
    with gzip.open(output / "records.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(
            {
                "records": records,
                "scenes": scenes,
                "assets": asset_records,
                "annotation_manifest": manifest,
            },
            stream,
            ensure_ascii=False,
        )
    sheet = Image.new("RGB", (8 * 96, 4 * 96))
    for i, image in enumerate(pixels[:32]):
        sheet.paste(Image.fromarray(image), (i % 8 * 96, i // 8 * 96))
    sheet.save(output / "actual-source-control-inputs.png")
    asset_sheet = source_gallery(crops)
    asset_sheet.save(output / "source-asset-crops.png")
    asset_sheet.close()
    for crop in crops:
        crop.close()
    for page in pages.values():
        page.close()
    report = {
        "status": "SOURCE_CONTROL_TENSORS_PREPARED_NOT_EVALUATED",
        "annotation_manifest_sha256": before,
        "answers": list(c.ANSWERS),
        "unique_source_assets": len(assets),
        "unique_pdf_books": len({s["pdf_sha256"] for s in sources.values()}),
        "unique_pdf_pages": len(sources),
        "paired_scenes": len(pixels),
        "questions": len(labels),
        "independent_source_examples": False,
        "fresh_original_rendering_verified": True,
        "training_or_calibration": False,
        "production_admitted": False,
        "dataset_sha256": sha(output / "dataset.npz"),
        "records_sha256": sha(output / "records.json.gz"),
        "source_crops_sha256": sha(output / "source-crops.npz"),
        "preparation_freeze_sha256": sha(output / "preparation-freeze.json"),
        "limits": manifest["limits"],
    }
    (output / "preparation-receipt.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {"file": p.name, "sha256": sha(p)}
                    for p in sorted(output.iterdir())
                    if p.is_file()
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "originals", "derived", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    prepare(
        args.manifest.resolve(),
        args.originals.resolve(),
        args.derived.resolve(),
        args.output.resolve(),
    )

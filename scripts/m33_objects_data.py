"""Acquire small licensed drawing subsets and render review sheets, not training gold.

QuickDraw's requested word and game recognition are proposals, not verified labels.
Only separately reviewed IDs may enter a prepared object curriculum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np

CLASSES = {
    "apple": "яблоко",
    "banana": "банан",
    "carrot": "морковь",
    "fish": "рыба",
    "tree": "дерево",
    "mug": "кружка",
    "chair": "стул",
    "book": "книга",
}
NEGATIVE = ("airplane", "bicycle", "cat", "flower")
BASE = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/"
LICENSE_URL = "https://raw.githubusercontent.com/googlecreativelab/quickdraw-dataset/master/LICENSE"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, data) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def raster(record: dict) -> np.ndarray:
    """Documented normalized strokes -> RGB; metadata never enters learned pixels."""
    from PIL import Image, ImageDraw

    drawing = record["drawing"]
    if not drawing or len(drawing) > 300:
        raise ValueError("Empty or excessively complex sketch")
    canvas = Image.new("RGB", (288, 288), "white")
    painter = ImageDraw.Draw(canvas)
    for stroke in drawing:
        if len(stroke) != 2 or len(stroke[0]) != len(stroke[1]) or not stroke[0]:
            raise ValueError("Malformed simplified stroke")
        points = [(float(x) + 16, float(y) + 16) for x, y in zip(*stroke, strict=True)]
        if any(not 16 <= v <= 271 for point in points for v in point):
            raise ValueError("Out-of-bounds stroke")
        if len(points) == 1:
            x, y = points[0]
            painter.ellipse((x - 2, y - 2, x + 2, y + 2), fill="black")
        else:
            painter.line(points, fill="black", width=5, joint="curve")
    return np.asarray(canvas.resize((96, 96), Image.Resampling.LANCZOS))


def acquire(root: Path, positive: int = 150, negative: int = 60) -> None:
    if root.exists():
        raise ValueError("Fresh acquisition directory required")
    if min(positive, negative) < 1 or max(positive, negative) > 1000:
        raise ValueError("Bounded acquisition budget required")
    root.mkdir(parents=True)
    raw = root / "raw"
    raw.mkdir()
    with urlopen(LICENSE_URL, timeout=30) as response:
        license_bytes = response.read(10000)
    if b"Creative Commons" not in license_bytes or b"4.0" not in license_bytes:
        raise ValueError("Unexpected licence; stop acquisition")
    (root / "LICENSE.quickdraw").write_bytes(license_bytes)
    files = []
    for category in (*CLASSES, *NEGATIVE):
        requested = positive if category in CLASSES else negative
        url = BASE + category + ".ndjson"
        output = raw / (category + ".ndjson")
        selected, scanned, ids = [], 0, set()
        with urlopen(url, timeout=45) as response, output.open("xb") as stream:
            metadata = dict(response.headers)
            for line in response:
                scanned += 1
                if scanned > requested * 10 or len(line) > 200000:
                    raise ValueError("Acquisition bounds exceeded")
                record = json.loads(line)
                if record["word"] != category:
                    raise ValueError("Unexpected requested category")
                if record.get("recognized") is not True:
                    continue
                identifier = str(record["key_id"])
                if identifier in ids:
                    raise ValueError("Repeated source identity")
                drawing = record.get("drawing")
                if not drawing or any(
                    len(stroke) != 2 or len(stroke[0]) != len(stroke[1])
                    for stroke in drawing
                ):
                    raise ValueError("Malformed simplified drawing")
                ids.add(identifier)
                stream.write(line)
                selected.append(identifier)
                if len(selected) == requested:
                    break
        if len(selected) != requested:
            raise ValueError("Insufficient source records")
        files.append(
            {
                "file": str(output.relative_to(root)),
                "url": url,
                "sha256": sha(output),
                "bytes": output.stat().st_size,
                "selected_ids": selected,
                "records_scanned": scanned,
                "response_metadata": metadata,
            }
        )
        print(
            json.dumps(
                {"category": category, "records": len(selected)}, ensure_ascii=False
            ),
            flush=True,
        )
    write_json(
        root / "acquisition.json",
        {
            "schema": 1,
            "licence": "CC BY 4.0",
            "licence_url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Quick, Draw! Dataset, made available by Google, Inc.; drawings contributed by game participants.",
            "documentation": "https://github.com/googlecreativelab/quickdraw-dataset",
            "modifications": "Small streamed subset; strokes rendered at RGB96x96 for review/training. Original selected NDJSON bytes retained.",
            "classes": CLASSES,
            "negative_categories": NEGATIVE,
            "files": files,
            "limits": "Requested category and recognized flag are unverified proposals, not human truth or model mastery.",
            "training_started": False,
        },
    )


def review_sheets(root: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    destination = root / "qa"
    destination.mkdir(exist_ok=False)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    manifest = json.loads((root / "acquisition.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = root / item["file"]
        if sha(path) != item["sha256"]:
            raise ValueError("Raw subset changed")
        rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        for start in range(0, len(rows), 75):
            canvas = Image.new("RGB", (10 * 112, 8 * 116), "white")
            draw = ImageDraw.Draw(canvas)
            for index, row in enumerate(rows[start : start + 75]):
                x, y = (index % 10) * 112, (index // 10) * 116
                canvas.paste(Image.fromarray(raster(row)), (x + 8, y))
                draw.text((x + 8, y + 97), str(start + index), font=font, fill="blue")
            canvas.save(destination / f"{path.stem}-{start:03d}.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--positive", type=int, default=150)
    parser.add_argument("--negative", type=int, default=60)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    acquire(args.output, args.positive, args.negative)
    if not args.no_render:
        review_sheets(args.output)

"""Render source pixels for known-development error inspection; not training data."""

import argparse
import json
from pathlib import Path

import numpy as np
from m33_objects_data import sha, write_json
from m33_objects_five_iterations import DATA
from m33_verify_objects_evidence import selected
from PIL import Image, ImageDraw, ImageFont


def render(data, diagnostic, output, *, count=24):
    if output.exists() or sha(data / "dataset.json") != DATA:
        raise ValueError("Fresh review output and frozen development data required")
    manifest = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    if sha(data / "pixels.npz") != manifest["pixels_sha256"]:
        raise ValueError("Review pixels changed")
    report = json.loads(diagnostic.read_text(encoding="utf-8"))
    candidate = next(k for k in report["candidates"] if k != "warm")
    rows = report["candidates"][candidate]["single_view"]["records"]
    failures = sorted(
        (
            r
            for r in rows
            if selected(r["probabilities"], 0) != r["gold"]
            and selected(r["probabilities"], 0) != "UNKNOWN"
        ),
        key=lambda r: max(r["probabilities"]),
        reverse=True,
    )[:count]
    pixels = np.load(data / "pixels.npz", allow_pickle=False)["dev_pixels"]
    indices = {r["source_id"]: i for i, r in enumerate(manifest["records"]["dev"])}
    width, height, columns = 270, 300, 6
    sheet = Image.new(
        "RGB",
        (columns * width, ((len(failures) + columns - 1) // columns) * height),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    records = []
    for number, row in enumerate(failures):
        x, y = (number % columns) * width, (number // columns) * height
        panel = Image.fromarray(pixels[indices[row["source_id"]]])
        sheet.paste(panel.resize((240, 240), Image.Resampling.NEAREST), (x + 15, y + 5))
        answer = selected(row["probabilities"], 0)
        draw.text(
            (x + 5, y + 248),
            f"{number + 1}. gold={row['gold']}, pred={answer}",
            fill="black",
            font=font,
        )
        draw.text(
            (x + 5, y + 267),
            f"p={max(row['probabilities']):.3f}",
            fill="black",
            font=font,
        )
        records.append(
            {
                "panel": number + 1,
                "source_id": row["source_id"],
                "gold": row["gold"],
                "raw_prediction": answer,
                "probability": max(row["probabilities"]),
                "pixel_sha256": manifest["records"]["dev"][indices[row["source_id"]]][
                    "pixel_sha256"
                ],
            }
        )
    sheet.save(output)
    write_json(
        output.with_suffix(".json"),
        {
            "status": "KNOWN_DEV_ERROR_INSPECTION_NOT_NEW_GOLD",
            "candidate": candidate,
            "checkpoint_sha256": report["candidates"][candidate]["checkpoint_sha256"],
            "diagnostic_sha256": sha(diagnostic),
            "sheet_sha256": sha(output),
            "records": records,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "diagnostic", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    render(args.data, args.diagnostic, args.output)

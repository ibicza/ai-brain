"""Pinned licensed color artwork proposals; visual review precedes admission."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

from m33_objects_data import CLASSES, sha, write_json
from PIL import Image, ImageDraw, ImageFont

PUBLISHERS = {
    "twemoji": {
        "repo": "jdecked/twemoji",
        "commit": "b6b55fef1e8636b540a6d016a4729ca8cdf2e60b",
        "path": "assets/72x72/{code}.png",
        "licence_file": "LICENSE-GRAPHICS",
        "licence": "CC BY 4.0",
        "attribution": "Twemoji artwork, Twitter and Jdecked contributors",
    },
    "noto": {
        "repo": "googlefonts/noto-emoji",
        "commit": "e20cbc2bbec1926686be9f9bee7d1d2cfa1fea0e",
        "path": "2D/png/128/emoji_u{code}.png",
        "licence_file": "LICENSE",
        "licence": "Apache-2.0",
        "attribution": "Noto Emoji artwork, Google and contributors",
    },
    "openmoji": {
        "repo": "hfg-gmuend/openmoji",
        "commit": "aeb8bb3a59e2de39c754ac79180c8131c906acea",
        "path": "color/72x72/{code}.png",
        "licence_file": "LICENSE.txt",
        "licence": "CC BY-SA 4.0",
        "attribution": "OpenMoji artwork, HfG Schwabisch Gmund and contributors",
    },
}
PROPOSALS = {
    "apple": ("1f34e", "1f34f"),
    "banana": ("1f34c",),
    "carrot": ("1f955",),
    "fish": ("1f41f", "1f420", "1f421"),
    "tree": ("1f332", "1f333", "1f334"),
    "mug": ("2615", "1f37a"),
    "chair": ("1fa91",),
    "book": ("1f4d5", "1f4d7", "1f4d8", "1f4d9", "1f4d6"),
    "pear": ("1f350",),
    "watermelon": ("1f349",),
    "cat": ("1f408",),
    "dog": ("1f415",),
    "rabbit": ("1f407",),
    "bird": ("1f426",),
    "grapes": ("1f347",),
    "cherries": ("1f352",),
    "flower": ("1f33c",),
    "car": ("1f697",),
    "bicycle": ("1f6b2",),
    "airplane": ("2708",),
    "moon": ("1f319",),
    "cloud": ("2601",),
    "circle": ("1f534",),
    "square": ("1f7e6",),
    "triangle": ("1f53a",),
}


def normalized(path):
    """Preserve full object and transparency on a white RGB canvas; no cropping."""
    image = Image.open(path).convert("RGBA")
    image.thumbnail((84, 84), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (96, 96), "white")
    canvas.alpha_composite(image, ((96 - image.width) // 2, (96 - image.height) // 2))
    return canvas.convert("RGB")


def acquire(root):
    if root.exists():
        raise ValueError("Fresh illustration acquisition required")
    root.mkdir(parents=True)
    sources = []
    for publisher, config in PUBLISHERS.items():
        base = f"https://raw.githubusercontent.com/{config['repo']}/{config['commit']}/"
        folder = root / publisher
        folder.mkdir()
        licence = folder / config["licence_file"]
        with urlopen(base + config["licence_file"], timeout=30) as response:
            licence.write_bytes(response.read(40000))
        for category, codes in PROPOSALS.items():
            for code in codes:
                formatted = code.upper() if publisher == "openmoji" else code
                sources.append(
                    {
                        "source_id": f"illustration/{publisher}/{code}",
                        "publisher": publisher,
                        "source_category": category,
                        "source_url": base + config["path"].format(code=formatted),
                        "source_file": str(folder / (code + ".png")),
                        "licence": config["licence"],
                        "licence_sha256": sha(licence),
                        "attribution": config["attribution"],
                        "commit": config["commit"],
                        # Related color/pose variants share an owner; publisher domain
                        # is fixed before training. OpenMoji remains an untouched style.
                        "declared_family": f"illustration/{publisher}/{category}",
                        "declared_split": "final"
                        if publisher == "openmoji"
                        else "train",
                        "proposed_answer": CLASSES.get(category, "UNKNOWN"),
                    }
                )

    def fetch(row):
        path = Path(row["source_file"])
        with urlopen(row["source_url"], timeout=45) as response:
            payload = response.read(500001)
        if len(payload) > 500000:
            raise ValueError("Illustration size budget exceeded")
        with path.open("xb") as stream:
            stream.write(payload)
        with Image.open(path) as image:
            if image.format != "PNG" or max(image.size) > 1024:
                raise ValueError("Unexpected illustration format")
            image.verify()
        return row | {"source_file_sha256": sha(path)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        acquired = list(pool.map(fetch, sources))
    write_json(
        root / "acquisition.json",
        {
            "schema": 1,
            "sources": acquired,
            "publishers": PUBLISHERS,
            "training_started": False,
            "limits": "Names/Unicode are proposals, not gold. Every source visually reviewed before admission. No external weights. Related variants grouped, OpenMoji entirely held out from training and development. Derived OpenMoji media retain CC BY-SA 4.0.",
        },
    )
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    qa = root / "qa"
    qa.mkdir()
    for publisher in PUBLISHERS:
        rows = [r for r in acquired if r["publisher"] == publisher]
        canvas = Image.new("RGB", (8 * 132, ((len(rows) + 7) // 8) * 130), "white")
        draw = ImageDraw.Draw(canvas)
        for i, row in enumerate(rows):
            x, y = (i % 8) * 132, (i // 8) * 130
            canvas.paste(normalized(row["source_file"]), (x + 18, y))
            draw.text(
                (x + 2, y + 98), row["source_id"].split("/")[-1], font=font, fill="blue"
            )
            draw.text((x + 2, y + 112), row["source_category"], font=font, fill="black")
        canvas.save(qa / (publisher + ".png"))
    return {"sources": len(acquired), "root": str(root)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output)))

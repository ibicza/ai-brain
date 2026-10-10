"""Cold unsupported-contour corpus; gold is offline, never an inference input.

Separate authored polygons sharing Pillow, not photographs or independent
human semantic annotation. This module is not imported by any training pilot.
"""

import hashlib

import numpy as np
from PIL import Image, ImageDraw

FAMILIES = ("semicircle", "teardrop", "chevron")
LABEL_DOMAIN = 0x4D334E4C
VISUAL_DOMAIN = 0x4D334E56


def contour(family):
    if family == "semicircle":
        return tuple((np.cos(t), np.sin(t)) for t in np.linspace(0, np.pi, 65))
    if family == "teardrop":
        return tuple(
            (np.sin(t) * (1 + np.cos(t)) / 1.3, -np.cos(t))
            for t in np.linspace(0, 2 * np.pi, 96, endpoint=False)
        )
    if family == "chevron":
        return ((-1, -0.8), (0, 0), (1, -0.8), (1, 0), (0, 0.9), (-1, 0))
    raise ValueError("Unregistered cold contour")


def render(scene, c):
    rng = np.random.default_rng(np.random.SeedSequence([scene["seed"], VISUAL_DOMAIN]))
    scale = 4
    bg = tuple(int(x) for x in rng.integers(210, 235, 3))
    canvas = Image.new("RGB", (384, 384), bg)
    for side, item in enumerate(scene["items"]):
        tile = 176
        radius = rng.uniform(11, 14.5) * scale
        mask = Image.new("L", (tile, tile))
        pen = ImageDraw.Draw(mask)
        center = tile / 2
        shape = item["shape"]
        if shape in c.SHAPES:
            ry = radius * (0.55 if shape in ("овал", "прямоугольник") else 1)
            box = (center - radius, center - ry, center + radius, center + ry)
            if shape in ("круг", "овал"):
                pen.ellipse(box, fill=255)
            else:
                pen.rectangle(box, fill=255)
        else:
            pen.polygon(
                [(center + radius * x, center + radius * y) for x, y in contour(shape)],
                fill=255,
            )
        mask = mask.rotate(
            float(rng.uniform(-70, 70)), resample=Image.Resampling.BICUBIC
        )
        pixels = np.asarray(mask)
        if (
            pixels[0].any()
            or pixels[-1].any()
            or pixels[:, 0].any()
            or pixels[:, -1].any()
        ):
            raise ValueError("Cold contour clipped")
        rgb = np.clip(
            np.asarray(c.RGB[c.COLORS.index(item["color"])]) + rng.uniform(-4, 4, 3),
            0,
            255,
        ).astype(int)
        surface = Image.new("RGB", mask.size, tuple(rgb))
        ink = tuple(np.clip(rgb + (-75 if rgb.mean() > 100 else 75), 0, 255))
        pen = ImageDraw.Draw(surface)
        if item["pattern"] == "полосатый":
            for y in range(0, tile, 28):
                pen.rectangle((0, y, tile, y + 6), fill=ink)
        elif item["pattern"] == "пятнистый":
            for y in range(16, tile, 32):
                for x in range(16, tile, 32):
                    pen.ellipse((x - 6.8, y - 6.8, x + 6.8, y + 6.8), fill=ink)
        cy = float(rng.uniform(29, 67))
        canvas.paste(
            surface, (int(((24, 72)[side] - 22) * scale), int((cy - 22) * scale)), mask
        )
        if item["hidden"]:
            ImageDraw.Draw(canvas).rectangle(
                (side * 192, 0, (side + 1) * 192 - 1, 383), fill=bg
            )
    return np.asarray(canvas.resize((96, 96), Image.Resampling.BOX)).copy()


def generate(count, seed, c):
    if (
        type(count) is not int
        or not 12 <= count <= 6000
        or type(seed) is not int
        or seed < 0
    ):
        raise ValueError("Fresh bounded cold corpus required")
    rng = np.random.default_rng(np.random.SeedSequence([seed, LABEL_DOMAIN]))
    scenes = []
    for i in range(count):
        items = []
        for side in (0, 1):
            shapes = c.SHAPES if (i + side) % 3 == 0 else FAMILIES
            items.append(
                {
                    "color": c.COLORS[int(rng.integers(len(c.COLORS)))],
                    "shape": shapes[int(rng.integers(len(shapes)))],
                    "pattern": c.PATTERNS[int(rng.integers(len(c.PATTERNS)))],
                    "hidden": (i + side * 3) % 13 == 0,
                }
            )
        scenes.append(
            {"identity": f"cold-contours/{i}", "seed": seed + i, "items": items}
        )
    pixels = np.stack([render(scene, c) for scene in scenes])
    records, questions, labels, indices = [], [], [], []
    for i, scene in enumerate(scenes):
        digest = hashlib.sha256(pixels[i].tobytes()).hexdigest()
        for side, item in enumerate(scene["items"]):
            for task in c.VALUES:
                value = item[task]
                label = (
                    c.UNKNOWN
                    if item["hidden"] or value not in c.VALUES[task]
                    else c.ANSWERS.index(value)
                )
                query = c.question(task, side, i % 3)
                records.append(
                    {
                        "scene_id": scene["identity"],
                        "image_sha256": digest,
                        "question": query,
                        "task": task,
                        "side": side,
                        "answer": label,
                        "family": item["shape"],
                    }
                )
                questions.append(c.encode_question(query))
                labels.append(label)
                indices.append(i)
    return {
        "pixels": pixels,
        "questions": np.asarray(questions, dtype=np.int64),
        "labels": np.asarray(labels, dtype=np.int64),
        "image_index": np.asarray(indices, dtype=np.int64),
        "records": records,
        "scenes": scenes,
    }

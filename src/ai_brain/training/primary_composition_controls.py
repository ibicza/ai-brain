"""A separate authored graphics family and out-of-answer-scope controls.

Offline geometry produces gold only. Images/questions alone enter the model.
Pillow is shared with the original rasterizer: not independent photographic gold.
Triangle/star can be known by a legacy course but are outside this readout's
four-shape answer scope. UNKNOWN here means unsupported by this particular head.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageDraw

from ai_brain.training import primary_composition as c

EXPOSURE_SHAPES = ("triangle", "cross")
EXTENDED_EXPOSURE_SHAPES = (*EXPOSURE_SHAPES, "hexagon", "heart", "arrow", "crescent")
PALETTE_EXPOSURE_SHAPES = (*EXTENDED_EXPOSURE_SHAPES, "parallelogram", "kite")
EXPOSURE_PROFILES = {
    "standard": EXPOSURE_SHAPES,
    "diverse": EXTENDED_EXPOSURE_SHAPES,
    "palette": PALETTE_EXPOSURE_SHAPES,
}
HELD_OUT_SHAPES = ("star", "pentagon", "trapezoid")
LABEL_RNG_DOMAIN = 0x4D33434C
PALETTE_LABEL_DOMAIN = 0x4D33504C
PALETTE_VISUAL_DOMAIN = 0x4D335056
PALETTE_UNKNOWN_RGB = {
    "оранжевый": (245, 140, 35),
    "розовый": (240, 135, 180),
    "голубой": (95, 205, 235),
    "фиолетовый": (150, 60, 190),
}
PALETTE_HELD_RGB = {"бирюзовый": (40, 190, 170)}
PALETTE_KNOWN_ENDPOINTS = {
    "красный": (245, 75, 65),
    "зелёный": (140, 220, 105),
    "жёлтый": (250, 235, 90),
    "синий": (35, 105, 230),
}


@dataclass(frozen=True)
class ControlItem:
    color: str
    shape: str
    pattern: str
    hidden: bool = False


@dataclass(frozen=True)
class ControlScene:
    identity: str
    seed: int
    items: tuple[ControlItem, ControlItem]
    renderer_profile: str = "standard"

    def validate(self):
        if (
            len(self.items) != 2
            or type(self.seed) is not int
            or self.seed < 0
            or self.renderer_profile not in ("standard", "palette")
        ):
            raise ValueError("Invalid authored control scene")
        for item in self.items:
            if (
                item.color not in (*c.COLORS, *PALETTE_UNKNOWN_RGB, *PALETTE_HELD_RGB)
                or (self.renderer_profile == "standard" and item.color not in c.COLORS)
                or item.shape
                not in (*c.SHAPES, *PALETTE_EXPOSURE_SHAPES, *HELD_OUT_SHAPES)
                or item.pattern not in c.PATTERNS
                or type(item.hidden) is not bool
            ):
                raise ValueError("Invalid authored control item")

    def gold(self, task, side):
        self.validate()
        if task not in c.VALUES or type(side) is not int or side not in (0, 1):
            raise ValueError("Invalid control question")
        item = self.items[side]
        value = getattr(item, task)
        return (
            c.UNKNOWN
            if item.hidden or value not in c.VALUES[task]
            else c.ANSWERS.index(value)
        )


def vertices(shape):
    """Normalized authored contours, intentionally different from training masks."""
    if shape == "triangle":
        return ((0, -1), (0.866, 0.5), (-0.866, 0.5))
    if shape == "cross":
        return (
            (-0.3, -1),
            (0.3, -1),
            (0.3, -0.3),
            (1, -0.3),
            (1, 0.3),
            (0.3, 0.3),
            (0.3, 1),
            (-0.3, 1),
            (-0.3, 0.3),
            (-1, 0.3),
            (-1, -0.3),
            (-0.3, -0.3),
        )
    if shape == "trapezoid":
        return ((-0.45, -0.9), (0.45, -0.9), (1, 0.9), (-1, 0.9))
    if shape == "parallelogram":
        return ((-1, -0.6), (0.45, -0.6), (1, 0.6), (-0.45, 0.6))
    if shape == "kite":
        return ((0, -1), (0.7, 0.15), (0, 0.8), (-0.7, 0.15))
    if shape == "arrow":
        return (
            (-1, -0.3),
            (0.15, -0.3),
            (0.15, -0.85),
            (1, 0),
            (0.15, 0.85),
            (0.15, 0.3),
            (-1, 0.3),
        )
    if shape == "hexagon":
        return tuple(
            (np.cos(t), np.sin(t)) for t in np.linspace(0, 2 * np.pi, 6, endpoint=False)
        )
    if shape == "heart":
        # Analytic heart inside [-1, 1]^2, not an ellipse with an incidental cue.
        return tuple(
            (
                np.sin(t) ** 3,
                -(
                    13 * np.cos(t)
                    - 5 * np.cos(2 * t)
                    - 2 * np.cos(3 * t)
                    - np.cos(4 * t)
                )
                / 18,
            )
            for t in np.linspace(0, 2 * np.pi, 64, endpoint=False)
        )
    if shape == "crescent":
        # Matched arc endpoints yield a simple concave polygon, not a hole mask.
        outer = [
            (np.cos(t), np.sin(t)) for t in np.linspace(np.pi / 3, 5 * np.pi / 3, 48)
        ]
        inner = [
            (0.5 - 0.65 * np.sin(t), 0.8660254037844386 * np.cos(t))
            for t in np.linspace(np.pi, 0, 32)
        ]
        return tuple(outer + inner)
    if shape in ("star", "pentagon"):
        n = 10 if shape == "star" else 5
        return tuple(
            (
                (0.42 if shape == "star" and i % 2 else 1)
                * np.cos(-np.pi / 2 + i * 2 * np.pi / n),
                (0.42 if shape == "star" and i % 2 else 1)
                * np.sin(-np.pi / 2 + i * 2 * np.pi / n),
            )
            for i in range(n)
        )
    raise ValueError("Not an authored polygon")


def render(scene):
    scene.validate()
    rng = np.random.default_rng(scene.seed)
    palette_rng = np.random.default_rng(
        np.random.SeedSequence([scene.seed, PALETTE_VISUAL_DOMAIN])
    )
    scale, size = 4, 96
    background = tuple(int(x) for x in rng.integers(210, 235, 3))
    if scene.renderer_profile == "palette":
        background = tuple(int(x) for x in palette_rng.integers(246, 256, 3))
    canvas = Image.new("RGB", (size * scale, size * scale), background)
    for side, item in enumerate(scene.items):
        radius = rng.uniform(11, 14.5) * scale
        mask = Image.new("L", (44 * scale, 44 * scale))
        pen = ImageDraw.Draw(mask)
        center = 22 * scale
        if item.shape in c.SHAPES:
            ry = radius * 0.55 if item.shape in ("овал", "прямоугольник") else radius
            box = (center - radius, center - ry, center + radius, center + ry)
            if item.shape in ("круг", "овал"):
                pen.ellipse(box, fill=255)
            else:
                pen.rectangle(box, fill=255)
        else:
            pen.polygon(
                [
                    (center + radius * x, center + radius * y)
                    for x, y in vertices(item.shape)
                ],
                fill=255,
            )
        mask = mask.rotate(
            float(rng.uniform(-70, 70)), resample=Image.Resampling.BICUBIC
        )
        # Whole mask remains inside its 44px tile, including the square diagonal.
        array = np.asarray(mask)
        if array[0].any() or array[-1].any() or array[:, 0].any() or array[:, -1].any():
            raise ValueError("Control contour clipped")
        # Consume historical draws unchanged; palette changes use another stream.
        jitter = rng.uniform(-4, 4, 3)
        base_rgb = (
            c.RGB[c.COLORS.index(item.color)]
            if item.color in c.COLORS
            else {**PALETTE_UNKNOWN_RGB, **PALETTE_HELD_RGB}[item.color]
        )
        rgb = np.asarray(base_rgb, dtype=float)
        if (
            scene.renderer_profile == "palette"
            and item.color in PALETTE_KNOWN_ENDPOINTS
        ):
            amount = palette_rng.uniform(0, 1)
            rgb = (
                rgb * (1 - amount)
                + np.asarray(PALETTE_KNOWN_ENDPOINTS[item.color]) * amount
            )
        rgb = np.clip(rgb + jitter, 0, 255).astype(int)
        surface = Image.new("RGB", mask.size, tuple(rgb))
        texture = ImageDraw.Draw(surface)
        ink = tuple(np.clip(rgb + (-75 if rgb.mean() > 100 else 75), 0, 255))
        if item.pattern == "полосатый":
            for y in range(0, 44 * scale, 7 * scale):
                texture.rectangle((0, y, 44 * scale, y + 1.5 * scale), fill=ink)
        elif item.pattern == "пятнистый":
            for y in range(4 * scale, 44 * scale, 8 * scale):
                for x in range(4 * scale, 44 * scale, 8 * scale):
                    texture.ellipse(
                        (
                            x - 1.7 * scale,
                            y - 1.7 * scale,
                            x + 1.7 * scale,
                            y + 1.7 * scale,
                        ),
                        fill=ink,
                    )
        cx, cy = (24, 72)[side], float(rng.uniform(29, 67))
        position = ((cx - 22) * scale, int((cy - 22) * scale))
        canvas.paste(surface, position, mask)
        if item.hidden:
            ImageDraw.Draw(canvas).rectangle(
                (side * 48 * scale, 0, (side + 1) * 48 * scale - 1, 96 * scale),
                fill=background,
            )
    return np.asarray(canvas.resize((size, size), Image.Resampling.BOX)).copy()


def scenes(
    split,
    count,
    seed,
    *,
    cohort=None,
    independent_labels=True,
    exposure_profile="standard",
):
    if (
        split not in ("exposure", "held_control")
        or type(count) is not int
        or count < 1
        or type(seed) is not int
        or seed < 0
        or type(independent_labels) is not bool
        or exposure_profile not in EXPOSURE_PROFILES
    ):
        raise ValueError("Invalid control corpus request")
    if cohort is not None and cohort not in (
        "exposure",
        "control_calibration",
        "control_dev",
        "control_final",
    ):
        raise ValueError("Invalid control cohort")
    unknown_shapes = (
        EXPOSURE_PROFILES[exposure_profile] if split == "exposure" else HELD_OUT_SHAPES
    )
    rng = np.random.default_rng(
        np.random.SeedSequence([seed, LABEL_RNG_DOMAIN]) if independent_labels else seed
    )
    palette_labels = np.random.default_rng(
        np.random.SeedSequence([seed, PALETTE_LABEL_DOMAIN])
    )
    rows = []
    for i in range(count):
        items = []
        for side in (0, 1):
            shapes = c.SHAPES if (i + side) % 3 == 0 else unknown_shapes
            shape = shapes[int(rng.integers(len(shapes)))]
            colors = [
                color
                for color in c.COLORS
                if split != "exposure" or (color, shape) not in c.HELD_COMBINATIONS
            ]
            color = colors[int(rng.integers(len(colors)))]
            if exposure_profile == "palette" and (i + side) % 3 == 1:
                unknown_colors = tuple(
                    PALETTE_HELD_RGB if split == "held_control" else PALETTE_UNKNOWN_RGB
                )
                color = unknown_colors[
                    int(palette_labels.integers(len(unknown_colors)))
                ]
            items.append(
                ControlItem(
                    color,
                    shape,
                    c.PATTERNS[int(rng.integers(3))],
                    (i + side * 3) % 13 == 0,
                )
            )
        rows.append(
            ControlScene(
                f"authored-{cohort or split}/{i}",
                seed + i,
                tuple(items),
                "palette" if exposure_profile == "palette" else "standard",
            )
        )
    return rows


def prepare(rows):
    pixels = np.stack([render(row) for row in rows])
    questions, labels, indices, records = [], [], [], []
    for i, scene in enumerate(rows):
        digest = hashlib.sha256(pixels[i].tobytes()).hexdigest()
        for side in (0, 1):
            for task in c.VALUES:
                text = c.question(task, side, i % 3)
                label = scene.gold(task, side)
                questions.append(c.encode_question(text))
                labels.append(label)
                indices.append(i)
                records.append(
                    {
                        "scene_id": scene.identity,
                        "image_sha256": digest,
                        "question": text,
                        "task": task,
                        "side": side,
                        "answer": label,
                    }
                )
    return {
        "pixels": pixels,
        "questions": np.asarray(questions, dtype=np.int64),
        "labels": np.asarray(labels, dtype=np.int64),
        "image_index": np.asarray(indices, dtype=np.int64),
        "records": records,
        "scenes": [asdict(row) for row in rows],
    }


def audit(auxiliary, native, *, exposure_profile="standard"):
    """All source seeds/IDs/pixels separate; unknown contour families held out."""
    if exposure_profile not in EXPOSURE_PROFILES:
        raise ValueError("Invalid control exposure profile")
    exposure_shapes = EXPOSURE_PROFILES[exposure_profile]
    seed_owners, identities, pixels = {}, {}, {}
    for split, group in {**native, **auxiliary}.items():
        for scene in group["scenes"]:
            if seed_owners.setdefault(scene["seed"], split) != split:
                raise ValueError("Auxiliary scene seed leakage")
            if identities.setdefault(scene["identity"], split) != split:
                raise ValueError("Auxiliary scene identity leakage")
            if split not in auxiliary:
                continue
            if scene.get("renderer_profile", "standard") != (
                "palette" if exposure_profile == "palette" else "standard"
            ):
                raise ValueError("Authored renderer profile differs from exposure")
            for item in scene["items"]:
                allowed_colors = (
                    (
                        *c.COLORS,
                        *(
                            PALETTE_HELD_RGB
                            if split == "control_final"
                            else PALETTE_UNKNOWN_RGB
                        ),
                    )
                    if exposure_profile == "palette"
                    else c.COLORS
                )
                if item["color"] not in allowed_colors:
                    raise ValueError(
                        "Held color entered exposure or unsupported color profile"
                    )
                if split != "control_final" and (
                    item["shape"] not in (*c.SHAPES, *exposure_shapes)
                    or (item["color"], item["shape"]) in c.HELD_COMBINATIONS
                ):
                    raise ValueError("Held control/combination entered exposure")
                if split == "control_final" and item["shape"] not in (
                    *c.SHAPES,
                    *HELD_OUT_SHAPES,
                ):
                    raise ValueError("Exposure contour entered held controls")
        for record in group["records"]:
            if pixels.setdefault(record["image_sha256"], split) != split:
                raise ValueError("Auxiliary pixel leakage")
    return {
        "unique_scene_seeds": len(seed_owners),
        "unique_scene_identities": len(identities),
        "unique_images": len(pixels),
        "exposure_shapes": exposure_shapes,
        "held_control_shapes": HELD_OUT_SHAPES,
        "exposure_unknown_colors": tuple(PALETTE_UNKNOWN_RGB)
        if exposure_profile == "palette"
        else (),
        "held_unknown_colors": tuple(PALETTE_HELD_RGB)
        if exposure_profile == "palette"
        else (),
        "limits": "Authored generator separation, shared Pillow, not external-source independence.",
    }

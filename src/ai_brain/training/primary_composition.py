"""Own, bounded attribute grounding on procedural scenes; not animal recognition.

Only RGB and question tokens enter inference. Renderer facts are offline gold.
One frozen inherited causal core is shared with the old courses. New words,
pixel residual and answer readout are experimental, not production admission.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch import nn

from ai_brain.training import primary_objects as old
from ai_brain.training import primary_zero as base

COLORS = (
    "красный",
    "синий",
    "зелёный",
    "жёлтый",
    "тёмно-зелёный",
    "коричневый",
    "белый",
    "чёрный",
)
RGB = (
    (215, 40, 45),
    (35, 80, 210),
    (35, 175, 70),
    (235, 200, 35),
    (15, 75, 35),
    (130, 75, 35),
    (242, 242, 240),
    (20, 20, 25),
)
SHAPES = base.SHAPES[:4]
PATTERNS = ("однотонный", "полосатый", "пятнистый")
VALUES = {"color": COLORS, "shape": SHAPES, "pattern": PATTERNS}
ANSWERS = (*COLORS, *SHAPES, *PATTERNS, "UNKNOWN")
UNKNOWN = len(ANSWERS) - 1
HELD_COMBINATIONS = {("зелёный", "овал"), ("синий", "квадрат")}
TEMPLATES = {
    "color": (
        "Какой цвет у {side} предмета?",
        "Назови цвет {side} предмета.",
        "What color is the {en} object?",
    ),
    "shape": (
        "Какая форма у {side} предмета?",
        "Назови форму {side} предмета.",
        "What shape is the {en} object?",
    ),
    "pattern": (
        "Какой узор у {side} предмета?",
        "Назови узор {side} предмета.",
        "What pattern is on the {en} object?",
    ),
}
QUERIES = {}
for _task, _templates in TEMPLATES.items():
    for _side, _ru, _en in ((0, "левого", "left"), (1, "правого", "right")):
        for _template in _templates:
            QUERIES[_template.format(side=_ru, en=_en)] = (_task, _side)
WORD_IDS = dict(old.WORD_IDS)
NEW_WORDS = sorted(
    {w for q in QUERIES for w in re.findall(r"[a-zа-яё]+|[.?]", q.lower())}
    - WORD_IDS.keys()
)
WORD_IDS.update({w: old.VOCAB_SIZE + i for i, w in enumerate(NEW_WORDS)})


def question(task: str, side: int, template: int = 0) -> str:
    if (
        task not in VALUES
        or type(side) is not int
        or side not in (0, 1)
        or type(template) is not int
        or not 0 <= template < 3
    ):
        raise ValueError("Unsupported bounded attribute question")
    return TEMPLATES[task][template].format(
        side=("левого", "правого")[side], en=("left", "right")[side]
    )


def encode_question(text: str) -> list[int]:
    if text not in QUERIES:
        raise ValueError("Outside supported composition language")
    tokens = re.findall(r"[a-zа-яё]+|[.?]", text.lower())
    if len(tokens) > base.QUESTION_LENGTH:
        raise ValueError("Question would be truncated")
    return (
        [WORD_IDS[w] for w in tokens]
        + [base.PAD_ID] * (base.QUESTION_LENGTH - len(tokens))
        + [base.READ_ID]
    )


@dataclass(frozen=True)
class Item:
    color: str
    shape: str
    pattern: str
    hidden: bool = False


@dataclass(frozen=True)
class Scene:
    identity: str
    seed: int
    items: tuple[Item, Item]
    style: str = "standard"

    def validate(self):
        if (
            len(self.items) != 2
            or self.style not in ("standard", "transfer")
            or type(self.seed) is not int
            or self.seed < 0
        ):
            raise ValueError("Invalid scene")
        for item in self.items:
            if (
                item.color not in COLORS
                or item.shape not in SHAPES
                or item.pattern not in PATTERNS
                or type(item.hidden) is not bool
            ):
                raise ValueError("Invalid visual attribute")

    def gold(self, task: str, side: int) -> int:
        self.validate()
        if task not in VALUES or type(side) is not int or side not in (0, 1):
            raise ValueError("Invalid attribute target")
        item = self.items[side]
        return UNKNOWN if item.hidden else ANSWERS.index(getattr(item, task))


def render(scene: Scene) -> np.ndarray:
    """Reproducible graphics with independent backgrounds; never annotated pixels."""
    scene.validate()
    rng = np.random.default_rng(scene.seed)
    scale, size = 3, base.IMAGE_SIZE
    background = tuple(int(v) for v in rng.integers(105, 175, 3))
    canvas = Image.new("RGB", (size * scale, size * scale), background)
    for side, item in enumerate(scene.items):
        cx, cy = (
            (24, 72)[side] + float(rng.uniform(-3, 3)),
            float(rng.uniform(36, 60)),
        )
        radius = float(rng.uniform(12, 17))
        rx, ry = (
            (radius, radius * 0.6)
            if item.shape in ("овал", "прямоугольник")
            else (radius, radius)
        )
        box = tuple(int(v * scale) for v in (cx - rx, cy - ry, cx + rx, cy + ry))
        mask = Image.new("L", canvas.size, 0)
        draw = ImageDraw.Draw(mask)
        if item.shape in ("круг", "овал"):
            draw.ellipse(box, fill=255)
        else:
            draw.rectangle(box, fill=255)
        rgb = np.array(RGB[COLORS.index(item.color)], dtype=float)
        rgb = tuple(int(v) for v in np.clip(rgb + rng.uniform(-8, 8, 3), 0, 255))
        surface = Image.new("RGB", canvas.size, rgb)
        pen = ImageDraw.Draw(surface)
        # Both light and dark markings occur, independently of shape/color.
        ink = tuple(
            int(v)
            for v in np.clip(
                np.array(rgb) + (-70 if rng.random() < 0.5 else 70), 0, 255
            )
        )
        if item.pattern == "полосатый":
            spacing, width = (
                int(rng.integers(6, 10)) * scale,
                int(rng.integers(2, 4)) * scale,
            )
            for x in range(box[0] - 80, box[2] + 80, spacing):
                slope = 24 * scale if scene.style == "transfer" else 0
                pen.line((x, box[1], x + slope, box[3]), fill=ink, width=width)
        elif item.pattern == "пятнистый":
            # Bounded jittered grid keeps the pattern visible at the actual 96px input.
            for x in range(box[0] + 4 * scale, box[2], 9 * scale):
                for y in range(box[1] + 3 * scale, box[3], 8 * scale):
                    xj, yj = (
                        x + int(rng.integers(-2, 3)) * scale,
                        y + int(rng.integers(-2, 3)) * scale,
                    )
                    r = (3 if scene.style == "transfer" else 2) * scale
                    pen.ellipse((xj - r, yj - r, xj + r, yj + r), fill=ink)
        canvas.paste(surface, (0, 0), mask)
        if item.hidden:
            # All attributes unknown. This does not pretend to simulate partial occlusion.
            ImageDraw.Draw(canvas).rectangle(
                (
                    4 * scale if side == 0 else 52 * scale,
                    15 * scale,
                    44 * scale if side == 0 else 92 * scale,
                    81 * scale,
                ),
                fill=(85, 85, 85),
            )
    return np.asarray(
        canvas.resize((size, size), Image.Resampling.LANCZOS), dtype=np.uint8
    ).copy()


def scenes(split: str, count: int, seed: int) -> list[Scene]:
    if (
        split
        not in ("train", "dev", "calibration", "final", "combinations", "transfer")
        or count < 1
        or seed < 0
    ):
        raise ValueError("Invalid corpus request")
    combos = [
        (c, s)
        for c in COLORS
        for s in SHAPES
        if ((c, s) in HELD_COMBINATIONS) == (split == "combinations")
    ]
    rows = []
    for i in range(count):
        rng = np.random.default_rng(seed + i)
        items = []
        for side in (0, 1):
            c, s = combos[int(rng.integers(len(combos)))]
            items.append(
                Item(
                    c,
                    s,
                    PATTERNS[int(rng.integers(len(PATTERNS)))],
                    (i + side * 3) % 11 == 0,
                )
            )
        rows.append(
            Scene(
                f"{split}/{i}",
                seed + i,
                tuple(items),
                "transfer" if split == "transfer" else "standard",
            )
        )
    return rows


def prepare(rows: list[Scene]) -> dict:
    pixels = np.stack([render(row) for row in rows])
    questions, labels, image_index, records = [], [], [], []
    for i, row in enumerate(rows):
        for side in (0, 1):
            for task in VALUES:
                text = question(task, side, i % 3)
                label = row.gold(task, side)
                questions.append(encode_question(text))
                labels.append(label)
                image_index.append(i)
                records.append(
                    {
                        "scene_id": row.identity,
                        "image_sha256": hashlib.sha256(pixels[i].tobytes()).hexdigest(),
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
        "image_index": np.asarray(image_index, dtype=np.int64),
        "records": records,
        "scenes": [asdict(r) for r in rows],
    }


def audit(data: dict) -> dict:
    owners = {}
    for split, group in data.items():
        for row in group["records"]:
            prior = owners.setdefault(row["image_sha256"], split)
            if prior != split:
                raise ValueError("Pixel leakage between composition splits")
        for scene in group["scenes"]:
            for item in scene["items"]:
                held = (item["color"], item["shape"]) in HELD_COMBINATIONS
                if held != (split == "combinations"):
                    raise ValueError("Held combination escaped its split")
    return {
        "unique_images": len(owners),
        "split_images": {k: len(v["pixels"]) for k, v in data.items()},
        "held_color_shape_pairs": sorted(HELD_COMBINATIONS),
        "limits": "Disjoint pixels/seeds, same procedural renderer family. Not independent photographic or textbook exam.",
    }


class CompositionModel(nn.Module):
    """New course uses the SAME inherited causal core, with bounded new readout."""

    def __init__(
        self, inherited: old.ObjectsModel, *, attribute_attention: bool = True
    ):
        super().__init__()
        if type(attribute_attention) is not bool:
            raise ValueError("Attribute attention flag must be boolean")
        self.attribute_attention_enabled = attribute_attention
        self.inherited = inherited
        for p in self.inherited.parameters():
            p.requires_grad_(False)
        width = inherited.core.config.d_model
        self.new_words = nn.Embedding(len(NEW_WORDS), width)
        self.pixel_residual = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(64, 64, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(64, width, 3, stride=2, padding=1),
        )
        nn.init.zeros_(self.pixel_residual[-1].weight)
        nn.init.zeros_(self.pixel_residual[-1].bias)
        if attribute_attention:
            # Learned word-to-pixel binding. Grid coordinates describe input
            # positions, not gold boxes, target IDs or renderer metadata.
            self.coordinate_embedding = nn.Linear(2, width)
            self.feature_norm = nn.LayerNorm(width)
            self.query_projection = nn.Sequential(
                nn.Linear(width, width), nn.GELU(), nn.LayerNorm(width)
            )
            self.attribute_attention = nn.MultiheadAttention(width, 4, batch_first=True)
            self.readout = nn.Sequential(
                nn.LayerNorm(width * 2),
                nn.Linear(width * 2, width * 2),
                nn.GELU(),
                nn.Linear(width * 2, len(ANSWERS)),
            )
        else:
            self.readout = nn.Linear(width, len(ANSWERS))
        texts = list(QUERIES)
        self.register_buffer(
            "supported_questions",
            torch.tensor([encode_question(q) for q in texts]),
            persistent=False,
        )
        allowed = torch.zeros(len(texts), len(ANSWERS), dtype=torch.bool)
        for i, text in enumerate(texts):
            task, _ = QUERIES[text]
            allowed[i, [ANSWERS.index(a) for a in VALUES[task]] + [UNKNOWN]] = True
        self.register_buffer("allowed_answers", allowed, persistent=False)

    def forward(self, images: torch.Tensor, questions: torch.Tensor):
        if (
            images.ndim != 4
            or images.shape[1:] != (3, base.IMAGE_SIZE, base.IMAGE_SIZE)
            or not images.is_floating_point()
            or not torch.isfinite(images).all()
            or torch.any((images < 0) | (images > 1))
        ):
            raise ValueError("Expected finite RGB [0,1] 96x96 pixels")
        if (
            questions.shape != (len(images), base.QUESTION_LENGTH + 1)
            or questions.dtype != torch.long
        ):
            raise ValueError("Invalid question tokens")
        matches = (questions[:, None] == self.supported_questions[None]).all(-1)
        if not matches.any(-1).all():
            raise ValueError("Unsupported composition question")
        features = self.inherited.vision(images) + self.pixel_residual(images)
        patches = features.flatten(2).transpose(1, 2)
        core = self.inherited.core
        positions = torch.arange(base.IMAGE_TOKENS, device=images.device)
        patches = (
            patches
            + core.position_embedding(positions)[None]
            + self.inherited.image_type
        )
        is_new = questions >= old.VOCAB_SIZE
        embeddings = core.token_embedding(questions.clamp(max=old.VOCAB_SIZE - 1))
        embeddings = torch.where(
            is_new[:, :, None],
            self.new_words((questions - old.VOCAB_SIZE).clamp(min=0)),
            embeddings,
        )
        words = (
            embeddings
            + core.position_embedding(
                torch.arange(questions.shape[1], device=images.device)
                + base.IMAGE_TOKENS
            )[None]
        )
        mask = questions[:, :-1] != base.PAD_ID
        summary = (embeddings[:, :-1] * mask[:, :, None]).sum(1) / mask.sum(
            1, keepdim=True
        ).clamp_min(1)
        words = words.clone()
        words[:, -1] = words[:, -1] + self.inherited.question_summary_norm(summary)
        key_mask = torch.cat(
            (
                torch.ones(
                    len(images),
                    base.IMAGE_TOKENS,
                    dtype=torch.bool,
                    device=images.device,
                ),
                questions != base.PAD_ID,
            ),
            dim=1,
        )
        _, hidden = core.forward_embeddings(
            torch.cat((patches, words), 1),
            attention_key_mask=key_mask,
            return_hidden=True,
        )
        if self.attribute_attention_enabled:
            axis = torch.linspace(-1, 1, features.shape[-1], device=images.device)
            yy, xx = torch.meshgrid(axis, axis, indexing="ij")
            coordinates = torch.stack((xx, yy), -1).reshape(-1, 2)
            visual = self.feature_norm(features.flatten(2).transpose(1, 2))
            keys = visual + self.coordinate_embedding(coordinates)[None]
            attended, _ = self.attribute_attention(
                self.query_projection(summary)[:, None],
                keys,
                visual,
                need_weights=False,
            )
            logits = self.readout(torch.cat((hidden[:, -1], attended[:, 0]), -1))
        else:
            logits = self.readout(hidden[:, -1])
        # Output scope depends only on input words, never on renderer facts.
        return logits.masked_fill(
            ~self.allowed_answers[matches.long().argmax(-1)], float("-inf")
        )

    def legacy_forward(self, images, questions):
        return self.inherited(images, questions)

    def train(self, mode: bool = True):
        super().train(mode)
        self.inherited.eval()
        return self

    def candidate_state(self):
        return {
            k: v.detach().cpu().clone()
            for k, v in self.state_dict().items()
            if not k.startswith("inherited.")
        }

    def load_candidate(self, state):
        expected = self.candidate_state()
        if set(state) != set(expected) or any(
            not isinstance(v, torch.Tensor)
            or v.shape != expected[k].shape
            or not torch.isfinite(v).all()
            for k, v in state.items()
        ):
            raise ValueError("Incomplete or incompatible course candidate")
        missing = self.load_state_dict(state, strict=False).missing_keys
        if any(not k.startswith("inherited.") for k in missing):
            raise ValueError("Unexpected missing course parameter")


def statistics(gold, predictions):
    if (
        not gold
        or len(gold) != len(predictions)
        or any(
            type(i) is not int or not 0 <= i < len(ANSWERS) for i in gold + predictions
        )
    ):
        raise ValueError("Invalid metric labels")
    accepted = sum(p != UNKNOWN for p in predictions)
    positive = sum(g != UNKNOWN for g in gold)
    false = sum(p != UNKNOWN and p != g for g, p in zip(gold, predictions, strict=True))
    correct = sum(
        p == g and g != UNKNOWN for g, p in zip(gold, predictions, strict=True)
    )
    n_unknown = len(gold) - positive
    return {
        "examples": len(gold),
        "accepted": accepted,
        "false_assertions": false,
        "accepted_error_rate": false / accepted if accepted else None,
        "answerable_recall": correct / positive if positive else None,
        "unknown_recall": sum(
            g == p == UNKNOWN for g, p in zip(gold, predictions, strict=True)
        )
        / n_unknown
        if n_unknown
        else None,
    }


def select(probabilities: np.ndarray, thresholds: list[float | None]) -> list[int]:
    values = np.asarray(probabilities)
    if (
        values.ndim != 2
        or values.shape[1] != len(ANSWERS)
        or len(thresholds) != len(values)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values.sum(1), 1, atol=1e-5)
    ):
        raise ValueError("Invalid probabilities")
    result = []
    for row, threshold in zip(values, thresholds, strict=True):
        if threshold is not None and (
            type(threshold) not in (int, float)
            or not np.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("Invalid abstention threshold")
        best = int(row.argmax())
        result.append(
            best if threshold is not None and row[best] >= threshold else UNKNOWN
        )
    return result


def describe(predictions: list[int]) -> dict:
    """Only accepted observations; no class-name lookup or hidden-anatomy inference."""
    if len(predictions) != 6 or any(
        type(p) is not int or not 0 <= p < len(ANSWERS) for p in predictions
    ):
        raise ValueError("Require six bounded observations")
    result = {
        "object_identity": "UNKNOWN",
        "scope": "Visible color/shape/pattern only; no animal identity, anatomy or general language.",
    }
    for side, name in ((0, "left"), (1, "right")):
        observations = {}
        for j, task in enumerate(VALUES):
            label = ANSWERS[predictions[side * 3 + j]]
            if label != "UNKNOWN" and label not in VALUES[task]:
                raise ValueError("Attribute answer outside its task")
            observations[task] = label
        result[name] = observations
    return result

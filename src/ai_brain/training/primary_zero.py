"""Own synthetic visual curriculum. Not a general textbook reader or truth oracle.

Pixels and a small Russian question are the only learned inputs. Scene metadata
is an offline renderer/label oracle and never enters the model forward pass.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn

from ai_brain.model.config import ModelConfig
from ai_brain.model.tiny_transformer import TinyCausalTransformer

SHAPES = ("круг", "овал", "квадрат", "прямоугольник", "треугольник", "звезда")
COLORS = ("красный", "синий", "зелёный", "жёлтый", "оранжевый", "фиолетовый")
RGB = (
    (210, 40, 45),
    (35, 80, 210),
    (35, 155, 65),
    (230, 195, 25),
    (235, 115, 25),
    (140, 45, 190),
)
ANSWERS = (*map(str, range(6)), *SHAPES, *COLORS, "UNKNOWN")
UNKNOWN = len(ANSWERS) - 1
TASKS = ("count", "shape", "color")
QUESTIONS = {
    "count": (
        "Сколько фигур на картинке?",
        "Сосчитай все фигуры.",
        "Сколько здесь фигур?",
        "Сколько всего фигур на картинке?",
        "Сколько фигур здесь на картинке?",
    ),
    "shape": (
        "Назови форму всех фигур.",
        "Какая общая форма у фигур?",
        "Какую форму имеют все фигуры?",
        "Назови общую форму фигур.",
        "Какую общую форму имеют фигуры?",
    ),
    "color": (
        "Назови цвет всех фигур.",
        "Какой общий цвет у фигур?",
        "Какого цвета все фигуры?",
        "Назови общий цвет фигур.",
        "Все фигуры какого цвета?",
    ),
}
PAD_ID, READ_ID = len(ANSWERS), len(ANSWERS) + 1
WORD_OFFSET = len(ANSWERS) + 2
# Static starter vocabulary from teaching questions only, not held-out text.
WORDS = sorted(
    {
        w
        for templates in QUESTIONS.values()
        for q in templates[:-1]
        for w in re.findall(r"[а-яё]+|[.?]", q.lower())
    }
)
VOCAB_SIZE = WORD_OFFSET + len(WORDS)
QUESTION_LENGTH = 12
IMAGE_SIZE = 96
IMAGE_TOKENS = (IMAGE_SIZE // 8) ** 2


def encode_question(question: str) -> list[int]:
    if question not in {q for values in QUESTIONS.values() for q in values}:
        raise ValueError("question outside the explicitly supported zero-class scope")
    words = re.findall(r"[а-яё]+|[.?]", question.lower())
    if len(words) > QUESTION_LENGTH:
        raise ValueError("question would be truncated")
    ids = [WORD_OFFSET + WORDS.index(word) for word in words]
    return ids + [PAD_ID] * (QUESTION_LENGTH - len(ids)) + [READ_ID]


@dataclass(frozen=True)
class ObjectSpec:
    shape: str
    color: str
    cx: float
    cy: float
    radius: float
    angle: float


@dataclass(frozen=True)
class Scene:
    scene_id: str
    seed: int
    style: str
    kind: str
    objects: tuple[ObjectSpec, ...]

    def validate(self) -> None:
        if self.style not in {"filled", "outlined", "shaded", "textured"}:
            raise ValueError("unknown rendering style")
        if self.kind not in {"normal", "mixed", "masked", "missing"}:
            raise ValueError("unknown scene kind")
        if not 0 <= len(self.objects) <= 5:
            raise ValueError("count outside zero-class range")
        for obj in self.objects:
            if obj.shape not in SHAPES or obj.color not in COLORS:
                raise ValueError("object outside admitted concept vocabulary")
            values = (obj.cx, obj.cy, obj.radius, obj.angle)
            if not all(math.isfinite(v) for v in values) or not 4 <= obj.radius <= 14:
                raise ValueError("invalid object geometry")
            if not (16 <= obj.cx <= 80 and 16 <= obj.cy <= 80):
                raise ValueError("object could be clipped")

    def gold(self, task: str) -> int:
        self.validate()
        if task not in TASKS:
            raise ValueError("unsupported task")
        if self.kind in {"missing", "masked"}:
            return UNKNOWN
        if task == "count":
            return len(self.objects)
        values = {getattr(obj, task) for obj in self.objects}
        if len(values) != 1:
            return UNKNOWN
        return ANSWERS.index(next(iter(values)))


def make_scene(
    split: str,
    index: int,
    *,
    seed: int,
    final_style: bool = False,
    independent_labels: bool = True,
) -> Scene:
    if type(independent_labels) is not bool:
        raise ValueError("Expected explicit label RNG policy")
    # Prevent label bits from reappearing in the textured renderer's noise.
    # False is reserved for reproducing archived original scenes.
    rng = np.random.default_rng(
        np.random.SeedSequence([seed, 0x4D335A4C]) if independent_labels else seed
    )
    kind = ("normal", "normal", "normal", "normal", "mixed", "masked", "missing")[
        index % 7
    ]
    count = int(rng.integers(0, 6))
    if kind == "mixed":
        count = max(count, 2)
    shape = SHAPES[int(rng.integers(len(SHAPES)))]
    color = COLORS[int(rng.integers(len(COLORS)))]
    cells = rng.permutation(6)[:count]
    objects = []
    # Half the scenes approximately equalize total area across different counts,
    # discouraging a "brighter / more filled area means more objects" shortcut.
    base_radius = float(rng.uniform(12, 13.5))
    for i, cell in enumerate(cells):
        radius = (
            base_radius / math.sqrt(max(count, 1))
            if index % 2
            else float(rng.uniform(7, 10))
        )
        objects.append(
            ObjectSpec(
                SHAPES[(SHAPES.index(shape) + i) % len(SHAPES)]
                if kind == "mixed"
                else shape,
                COLORS[(COLORS.index(color) + i) % len(COLORS)]
                if kind == "mixed"
                else color,
                float(19 + (cell % 3) * 29 + rng.uniform(-1, 1)),
                float(25 + (cell // 3) * 45 + rng.uniform(-2, 2)),
                radius,
                float(rng.uniform(-0.25, 0.25)),
            )
        )
    return Scene(
        f"{split}/{index}",
        seed,
        "textured" if final_style else ("filled", "outlined", "shaded")[index % 3],
        kind,
        tuple(objects),
    )


def _polygon(
    x: np.ndarray, y: np.ndarray, vertices: list[tuple[float, float]]
) -> np.ndarray:
    inside = np.zeros(x.shape, dtype=bool)
    for (ax, ay), (bx, by) in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        if ay != by:
            inside ^= ((ay > y) != (by > y)) & (
                x < (bx - ax) * (y - ay) / (by - ay) + ax
            )
    return inside


def _mask(obj: ObjectSpec) -> np.ndarray:
    yy, xx = np.mgrid[:IMAGE_SIZE, :IMAGE_SIZE]
    xx, yy = xx - obj.cx, yy - obj.cy
    x = (xx * math.cos(obj.angle) + yy * math.sin(obj.angle)) / obj.radius
    y = (-xx * math.sin(obj.angle) + yy * math.cos(obj.angle)) / obj.radius
    if obj.shape == "круг":
        return x * x + y * y <= 1
    if obj.shape == "овал":
        return (x / 1.2) ** 2 + (y / 0.7) ** 2 <= 1
    if obj.shape == "квадрат":
        return (np.abs(x) <= 0.8) & (np.abs(y) <= 0.8)
    if obj.shape == "прямоугольник":
        return (np.abs(x) <= 1.1) & (np.abs(y) <= 0.55)
    if obj.shape == "треугольник":
        return _polygon(x, y, [(0, -1), (0.95, 0.85), (-0.95, 0.85)])
    vertices = [
        (
            (1 if i % 2 == 0 else 0.45) * math.cos(i * math.pi / 5 - math.pi / 2),
            (1 if i % 2 == 0 else 0.45) * math.sin(i * math.pi / 5 - math.pi / 2),
        )
        for i in range(10)
    ]
    return _polygon(x, y, vertices)


def render(scene: Scene) -> tuple[np.ndarray, list[dict]]:
    scene.validate()
    rng = np.random.default_rng(scene.seed)
    background = 246 if scene.style != "textured" else 230
    image = np.full((IMAGE_SIZE, IMAGE_SIZE, 3), background, dtype=np.uint8)
    if scene.style == "textured":
        noise = rng.integers(-5, 6, image.shape[:2])
        image = np.clip(image.astype(np.int16) + noise[:, :, None], 0, 255).astype(
            np.uint8
        )
    occupied = np.zeros(image.shape[:2], dtype=bool)
    evidence = []
    for obj in scene.objects:
        mask = _mask(obj)
        if mask.sum() < 8 or np.any(occupied & mask):
            raise ValueError("unreadable or overlapping synthetic object")
        occupied |= mask
        eroded = mask.copy()
        eroded[1:] &= mask[:-1]
        eroded[:-1] &= mask[1:]
        eroded[:, 1:] &= mask[:, :-1]
        eroded[:, :-1] &= mask[:, 1:]
        if scene.style == "outlined":
            image[mask & ~eroded] = RGB[COLORS.index(obj.color)]
        else:
            image[mask] = RGB[COLORS.index(obj.color)]
            if scene.style in {"shaded", "textured"}:
                image[mask & ~eroded] = (45, 45, 45)
        ys, xs = np.nonzero(mask)
        evidence.append(
            {
                "bbox_xyxy": [
                    int(xs.min()),
                    int(ys.min()),
                    int(xs.max()) + 1,
                    int(ys.max()) + 1,
                ],
                "pixels": int(mask.sum()),
                "shape": obj.shape,
                "color": obj.color,
            }
        )
    if scene.kind == "masked":
        # Visible occluder; hidden count/attributes must not be used as labels.
        image[3:-3, 3:-3] = (80, 80, 80)
        image[3:-3:4, 3:-3] = (115, 115, 115)
        evidence = []
    elif scene.kind == "missing":
        image[:] = 0
        evidence = []
    return image, evidence


@dataclass(frozen=True)
class Sample:
    scene: Scene
    image_sha256: str
    task: str
    question: str
    answer: int

    def validate(self) -> None:
        if self.task not in TASKS or self.question not in QUESTIONS[self.task]:
            raise ValueError("task/question mismatch")
        encode_question(self.question)
        image, _ = render(self.scene)
        if self.image_sha256 != hashlib.sha256(image.tobytes()).hexdigest():
            raise ValueError("pixel hash mismatch")
        if self.answer != self.scene.gold(self.task):
            raise ValueError("oracle answer mismatch")


def corpus(
    *, train_scenes: int = 1800, holdout_scenes: int = 420, round_id: int = 1
) -> dict[str, list[Sample]]:
    if train_scenes < 7 or holdout_scenes < 7 or round_id < 1:
        raise ValueError("invalid curriculum sizes/round")
    result = {}
    for offset, split in enumerate(
        ("train", "dev", "calibration", "final", "transfer")
    ):
        rows = []
        for i in range(train_scenes if split == "train" else holdout_scenes):
            scene = make_scene(
                split,
                i,
                seed=round_id * 1_000_000 + offset * 100_000 + i,
                final_style=split == "transfer",
            )
            image, _ = render(scene)
            digest = hashlib.sha256(image.tobytes()).hexdigest()
            for task in TASKS:
                question = QUESTIONS[task][
                    -1
                    if split in {"final", "transfer"}
                    else i % (len(QUESTIONS[task]) - 1)
                ]
                rows.append(Sample(scene, digest, task, question, scene.gold(task)))
        result[split] = rows
    return result


def audit_splits(splits: dict[str, list[Sample]]) -> dict:
    if set(splits) != {"train", "dev", "calibration", "final", "transfer"}:
        raise ValueError("require five separate splits")
    owners: dict[str, str] = {}
    report = {}
    # Pixel-identical uninformative inputs are deliberately shared UNKNOWN
    # controls; known normal-empty backgrounds are also fixed constant inputs.
    # They are not counted as independent learned source families.
    for split, rows in splits.items():
        if not rows:
            raise ValueError("empty split")
        for row in rows:
            row.validate()
            if row.scene.kind not in {"masked", "missing"} and row.scene.objects:
                prior = owners.setdefault(row.image_sha256, split)
                if prior != split:
                    raise ValueError("nontrivial pixel leakage across splits")
        report[split] = {
            "examples": len(rows),
            "scenes": len({r.scene.scene_id for r in rows}),
            "labels": dict(Counter(ANSWERS[r.answer] for r in rows)),
        }
    return {
        "splits": report,
        "constant_controls_shared": True,
        "semantic_duplicate_detection": "NOT_IMPLEMENTED; procedural styles only, not independent textbooks",
    }


class ZeroClassModel(nn.Module):
    """CNN pixels + learned Russian starter words -> shared causal core -> answer."""

    def __init__(self, *, width: int = 64, layers: int = 2) -> None:
        super().__init__()
        config = ModelConfig(
            vocab_size=VOCAB_SIZE,
            max_sequence_length=IMAGE_TOKENS + QUESTION_LENGTH + 1,
            d_model=width,
            num_layers=layers,
            num_heads=4,
            ffn_hidden_dim=width * 4,
            tie_embeddings=False,
        )
        self.core = TinyCausalTransformer(config)
        self.vision = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=1, padding=1),
            nn.GELU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 32, 3, stride=1, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(64, width, 3, stride=2, padding=1),
            nn.GELU(),
        )
        self.image_type = nn.Parameter(torch.zeros(1, 1, width))
        self.question_intent = nn.Linear(width, len(TASKS))
        self.question_summary_norm = nn.LayerNorm(width)

    def forward(
        self,
        images: torch.Tensor,
        questions: torch.Tensor,
        *,
        return_intent: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        if images.ndim != 4 or images.shape[1:] != (3, IMAGE_SIZE, IMAGE_SIZE):
            raise ValueError("expected RGB 96x96 image batch")
        if questions.shape != (images.shape[0], QUESTION_LENGTH + 1):
            raise ValueError("invalid question tensor shape")
        patches = self.visual_features(images, questions).flatten(2).transpose(1, 2)
        positions = torch.arange(IMAGE_TOKENS, device=images.device)
        patches = (
            patches + self.core.position_embedding(positions)[None] + self.image_type
        )
        words = self.core.embed_tokens_and_positions(
            questions, position_offset=IMAGE_TOKENS
        )
        # Learned starter-word summary, not a task-ID parser. Ordered tokens
        # remain available; this limited helper does not prove general language.
        word_mask = questions[:, :-1] != PAD_ID
        embeddings = self.core.token_embedding(questions[:, :-1])
        summary = (embeddings * word_mask[:, :, None]).sum(1) / word_mask.sum(
            1, keepdim=True
        ).clamp_min(1)
        summary = self.question_summary_norm(summary)
        words[:, -1] = words[:, -1] + summary
        key_mask = torch.cat(
            (
                torch.ones(
                    images.shape[0],
                    IMAGE_TOKENS,
                    dtype=torch.bool,
                    device=images.device,
                ),
                questions != PAD_ID,
            ),
            dim=1,
        )
        logits = self.answer_logits(
            torch.cat((patches, words), dim=1), key_mask, questions
        )
        return (logits, self.question_intent(summary)) if return_intent else logits

    def visual_features(
        self, images: torch.Tensor, questions: torch.Tensor
    ) -> torch.Tensor:
        """Overridable pixel feature stage; original course remains unchanged."""
        return self.vision(images)

    def answer_logits(self, embeddings, key_mask, questions):
        """Shared causal-core answer stage; baseline computation is unchanged."""
        return self.core.forward_embeddings(embeddings, attention_key_mask=key_mask)[
            :, -1
        ]


def consensus_probabilities(views: list[list[float]]) -> list[float]:
    """Agreeing views keep the weakest confidence; remainder becomes uncertainty."""
    if len(views) < 2:
        raise ValueError("require at least two visual views")
    for view in views:
        select_answer(view, 0)
    best = {int(np.argmax(view)) for view in views}
    result = [0.0] * VOCAB_SIZE
    if len(best) != 1 or next(iter(best)) >= len(ANSWERS):
        result[UNKNOWN] = 1.0
    else:
        label = next(iter(best))
        confidence = min(view[label] for view in views)
        result[label] = confidence
        result[UNKNOWN] += 1 - confidence
    return result


def select_answer(probabilities: list[float], threshold: float | None) -> int:
    values = np.asarray(probabilities, dtype=float)
    if (
        values.shape != (VOCAB_SIZE,)
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.isclose(values.sum(), 1, atol=1e-5)
    ):
        raise ValueError("invalid full-vocabulary probabilities")
    if threshold is None:
        return UNKNOWN
    if not 0 <= threshold <= 1:
        raise ValueError("invalid threshold")
    best = int(values.argmax())
    # Invalid output tokens and their probability mass are never renormalized.
    return best if best < len(ANSWERS) and values[best] >= threshold else UNKNOWN


def metrics(gold: list[int], predicted: list[int]) -> dict:
    if (
        not gold
        or len(gold) != len(predicted)
        or any(
            type(v) is not int or not 0 <= v < len(ANSWERS) for v in gold + predicted
        )
    ):
        raise ValueError("invalid metric labels")
    accepted = sum(p != UNKNOWN for p in predicted)
    answerable = sum(g != UNKNOWN for g in gold)
    unknown = len(gold) - answerable
    return {
        "examples": len(gold),
        "accepted": accepted,
        "false_assertions": sum(
            p != UNKNOWN and p != g for g, p in zip(gold, predicted, strict=True)
        ),
        "accuracy": sum(g == p for g, p in zip(gold, predicted, strict=True))
        / len(gold),
        "answerable_recall": sum(
            g == p and g != UNKNOWN for g, p in zip(gold, predicted, strict=True)
        )
        / answerable
        if answerable
        else None,
        "unknown_recall": sum(
            g == p == UNKNOWN for g, p in zip(gold, predicted, strict=True)
        )
        / unknown
        if unknown
        else None,
    }


def calibrate(
    rows: list[Sample], probabilities: list[list[float]], *, min_accepted: int = 50
) -> dict[str, float | None]:
    if len(rows) != len(probabilities) or min_accepted < 1:
        raise ValueError("invalid calibration inputs")
    thresholds = {}
    for task in TASKS:
        indices = [i for i, row in enumerate(rows) if row.task == task]
        gold = [rows[i].answer for i in indices]
        choices = []
        for threshold in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995):
            stats = metrics(
                gold, [select_answer(probabilities[i], threshold) for i in indices]
            )
            if not stats["false_assertions"] and stats["accepted"] >= min_accepted:
                choices.append((stats["accepted"], threshold))
        thresholds[task] = max(choices)[1] if choices else None
    return thresholds


def sample_record(sample: Sample) -> dict:
    record = asdict(sample)
    record["answer_text"] = ANSWERS[sample.answer]
    record["provenance"] = "OWN_PROCEDURAL_SCENE_ORACLE_NOT_AGENT_PSEUDOLABEL"
    record["scope"] = "bounded Russian shape/color/count pilot; not school knowledge"
    return record

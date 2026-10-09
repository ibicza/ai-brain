"""Remote-friendly incremental own-weight object pilot with frozen final evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path

import numpy as np
import torch
from m33_primary_relations_pilot import Prepared as OldPrepared
from m33_primary_relations_pilot import (
    brightness_view,
    translated_view,
)
from m33_primary_relations_pilot import (
    probabilities as old_probabilities,
)
from m33_primary_relations_pilot import (
    summarize as old_summarize,
)
from torch.nn import functional as F

from ai_brain.training import primary_objects as obj
from ai_brain.training import primary_relations as old
from ai_brain.training.primary_object_augmentation import background_view, diverse_view

PREVIOUS_SHA = "a4a168a362f6afb20b9dc579ad91c47ca725ab0cbadb6a556a3d6e257e6c1fae"
POLICY_SHA = "21529d9cfd6e0b71f0fd58b6694dd3d32b7d680fd91d7bb002491c9c635591f6"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class ObjectPrepared:
    def __init__(self, archive, split, device):
        pixels = archive[split + "_pixels"]
        if (
            pixels.dtype != np.uint8
            or pixels.ndim != 4
            or pixels.shape[1:] != (96, 96, 3)
        ):
            raise ValueError("Invalid RGB object pixels")
        names = archive[split + "_answers"].tolist()
        self.ids = archive[split + "_ids"].tolist()
        self.images = torch.from_numpy(pixels.copy()).permute(0, 3, 1, 2).to(device)
        final = split in ("final", "regression", "textbook_diagnostic")
        indices = (6, 7) if final else tuple(range(6))
        self.texts = [
            obj.OBJECT_QUESTIONS[indices[i % len(indices)]] for i in range(len(names))
        ]
        self.questions = torch.tensor(
            [obj.encode_question(text) for text in self.texts], device=device
        )
        self.answers = torch.tensor(
            [
                obj.UNKNOWN if name == "UNKNOWN" else obj.OBJECT_IDS[name]
                for name in names
            ],
            device=device,
        )
        self.tasks = ["object"] * len(names)
        if len(self.ids) != len(names) or pixels.shape[0] != len(names):
            raise ValueError("Object data alignment mismatch")

    def batch(self, ids):
        return self.images[ids].float() / 255, self.questions[ids], self.answers[ids]


def tasks(data):
    return (
        data.tasks
        if isinstance(data, ObjectPrepared)
        else [row.task for row in data.rows]
    )


@torch.no_grad()
def probabilities(model, data, *, consensus=True, mode="normal"):
    model.eval()
    output = []
    for start in range(0, len(data.answers), 128):
        ids = torch.arange(
            start, min(start + 128, len(data.answers)), device=data.answers.device
        )
        images, questions, _ = data.batch(ids)
        if mode == "blank":
            images = torch.zeros_like(images)
        elif mode == "shuffled":
            other = (ids + 17) % len(data.answers)
            images = data.batch(other)[0]
        elif mode != "normal":
            raise ValueError("Invalid evaluation mode")
        primary = model(images, questions).softmax(-1).cpu().tolist()
        if consensus:
            views = [primary]
            for view in (
                brightness_view(images),
                translated_view(images, 1, 1),
                translated_view(images, -1, -1),
            ):
                views.append(model(view, questions).softmax(-1).cpu().tolist())
            views.append(
                model(images.flip(-1), old.mirror_questions(questions))
                .softmax(-1)
                .cpu()
                .tolist()
            )
            primary = [
                obj.consensus_probabilities(items) for items in zip(*views, strict=True)
            ]
        output.extend(primary)
    return output


def selected(data, probs, thresholds):
    return [
        obj.select_answer(p, thresholds[task])
        for p, task in zip(probs, tasks(data), strict=True)
    ]


def summary(data, probs, thresholds):
    answers = data.answers.cpu().tolist()
    predicted = selected(data, probs, thresholds)
    task_names = tasks(data)
    result = {"all": obj.metrics(answers, predicted)}
    for task in set(task_names):
        indices = [i for i, value in enumerate(task_names) if value == task]
        result[task] = obj.metrics(
            [answers[i] for i in indices], [predicted[i] for i in indices]
        )
    if isinstance(data, ObjectPrepared):
        result["by_concept"] = {}
        for word, identifier in obj.OBJECT_IDS.items():
            indices = [i for i, value in enumerate(answers) if value == identifier]
            if indices:
                result["by_concept"][word] = obj.metrics(
                    [answers[i] for i in indices], [predicted[i] for i in indices]
                )
    return result


def loss_on(data, probs):
    return float(
        -np.mean(
            [
                np.log(max(p[g], 1e-30))
                for p, g in zip(probs, data.answers.cpu().tolist(), strict=True)
            ]
        )
    )


def domain_balanced_loss(data, probs, records, *, class_balanced=False):
    """Development-only domains have equal weight, irrespective of row count."""
    if len(records) != len(probs) or len(probs) != len(data.answers):
        raise ValueError("Development domain alignment mismatch")
    domains = {}
    for row, probability, label in zip(
        records, probs, data.answers.cpu().tolist(), strict=True
    ):
        role = row["role"]
        name = (
            "photo"
            if role == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
            else "illustration"
            if role == "VISUALLY_CURATED_NONBLIND_COLOR_ILLUSTRATION"
            else "sketch_and_control"
        )
        domains.setdefault(name, {}).setdefault(label, []).append(
            -math.log(max(probability[label], 1e-30))
        )
    if class_balanced:
        return sum(
            sum(sum(v) / len(v) for v in labels.values()) / len(labels)
            for labels in domains.values()
        ) / len(domains)
    return sum(
        sum(sum(v) for v in labels.values()) / sum(len(v) for v in labels.values())
        for labels in domains.values()
    ) / len(domains)


def verify_inherited(model, source_state):
    for name, value in source_state.items():
        current = model.state_dict()[name].cpu()
        inherited = (
            current[: value.shape[0]] if current.shape != value.shape else current
        )
        if not torch.equal(inherited, value.cpu()):
            raise ValueError("Protected inherited tensor changed: " + name)


def verify_inputs(args, protocol):
    if (
        sha(args.previous) != PREVIOUS_SHA
        or sha(args.previous_policy) != POLICY_SHA
        or sha(args.data / "pixels.npz") != protocol["pixels_sha256"]
        or sha(args.data / "dataset.json") != protocol["dataset_sha256"]
    ):
        raise ValueError("Immutable inputs changed during experiment")
    if args.warm_start and sha(args.warm_start) != protocol["warm_start_sha256"]:
        raise ValueError("Warm-start own checkpoint changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--previous-policy", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10000)
    parser.add_argument("--eval-every", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    parser.add_argument("--round-id", type=int, default=10901)
    parser.add_argument("--train-scenes", type=int, default=1200)
    parser.add_argument("--holdout-scenes", type=int, default=300)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--protect-inherited", action="store_true")
    parser.add_argument(
        "--vision-extension-channels", type=int, choices=(0, 32, 64, 128), default=0
    )
    parser.add_argument(
        "--vision-extension-depth", type=int, choices=(0, 1, 2), default=0
    )
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument("--object-unknown-adapter", action="store_true")
    parser.add_argument("--vision-global-context", action="store_true")
    parser.add_argument("--object-readout-adapter", action="store_true")
    parser.add_argument("--warm-start", type=Path)
    parser.add_argument("--diversity-augmentation", action="store_true")
    parser.add_argument("--background-augmentation", action="store_true")
    parser.add_argument("--illustration-fraction", type=float, default=0)
    parser.add_argument("--domain-balanced-dev", action="store_true")
    parser.add_argument("--class-domain-balanced-dev", action="store_true")
    parser.add_argument("--evaluate-checkpoint", type=Path)
    parser.add_argument("--selection-receipt", type=Path)
    parser.add_argument(
        "--evaluation-note",
        default="Known v1 object regression cohort, not a fresh blind exam.",
    )
    args = parser.parse_args()
    if (
        args.output.exists()
        or args.eval_every < 1
        or (args.steps < 1 and not args.evaluate_checkpoint)
        or args.learning_rate <= 0
        or not 0 <= args.illustration_fraction <= 0.75
        or (args.class_domain_balanced_dev and not args.domain_balanced_dev)
        or (
            args.warm_start and (not args.protect_inherited or args.evaluate_checkpoint)
        )
        or (
            (
                args.vision_extension_channels
                or args.object_unknown_adapter
                or args.vision_global_context
                or args.object_readout_adapter
            )
            and not args.protect_inherited
        )
    ):
        raise ValueError("Fresh experiment and valid budget required")
    if args.evaluate_checkpoint:
        if args.steps != 0 or args.development_only or not args.selection_receipt:
            raise ValueError(
                "Frozen evaluation requires steps=0 and predeclared selection receipt"
            )
    elif args.selection_receipt:
        raise ValueError("Selection receipt only valid for frozen evaluation")
    if sha(args.previous) != PREVIOUS_SHA or sha(args.previous_policy) != POLICY_SHA:
        raise ValueError("Unverified previous own checkpoint/policy")
    manifest = json.loads((args.data / "dataset.json").read_text(encoding="utf-8"))
    if sha(args.data / "pixels.npz") != manifest["pixels_sha256"]:
        raise ValueError("Dataset pixels changed")
    if tuple(manifest["classes"].values()) != obj.OBJECTS:
        raise ValueError("Object scope mismatch")
    if args.evaluate_checkpoint:
        receipt = json.loads(args.selection_receipt.read_text(encoding="utf-8"))
        winner = receipt["winner"]
        expected_architecture = {
            "vision_extension_channels": args.vision_extension_channels,
            "vision_extension_depth": args.vision_extension_depth,
        }
        if args.object_unknown_adapter:
            expected_architecture["object_unknown_adapter"] = True
        if args.vision_global_context:
            expected_architecture["vision_global_context"] = True
        if args.object_readout_adapter:
            expected_architecture["object_readout_adapter"] = True
        if (
            winner["checkpoint_sha256"] != sha(args.evaluate_checkpoint)
            or receipt["dataset_sha256"] != sha(args.data / "dataset.json")
            or receipt["selection_used"] != "DEVELOPMENT_ONLY"
            or winner["architecture"] != expected_architecture
            or receipt["round_id"] != args.round_id
        ):
            raise ValueError("Frozen winner/selection boundary mismatch")
    device = torch.device(args.device)
    if args.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; no silent fallback")
    torch.set_num_threads(2)
    torch.manual_seed(20261009 + args.round_id)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    args.output.mkdir(parents=True)
    protocol = {
        "schema": 1,
        "scope": "OWN_EIGHT_OBJECT_SCHEMATIC_PILOT_NOT_GENERAL_SIGHT_OR_M33_CLOSURE",
        "config": {
            k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()
        },
        "previous_sha256": PREVIOUS_SHA,
        "previous_policy_sha256": POLICY_SHA,
        "warm_start_sha256": sha(args.warm_start) if args.warm_start else None,
        "dataset_sha256": sha(args.data / "dataset.json"),
        "pixels_sha256": manifest["pixels_sha256"],
        "capsule_sha256": os.environ.get("AI_BRAIN_CAPSULE_SHA256", "LOCAL_NO_CAPSULE"),
        "learned_inputs": "RGB96x96 and supported RU/EN question tokens only; source/category/gold/task never forward inputs. Object answers use Russian names.",
        "weights": "Continue own accepted seven-skill checkpoint; append answer/word/intent IDs; one inherited core; no external pretrained weights.",
        "replay": "Fresh procedural seven-skill scenes; old teacher soft targets only on correct training examples confidence>=.98. Half batch new objects, eighth color, remainder old joint tasks.",
        "selection": "minimum .5 object-dev CE + .5 replay-dev CE; domain_balanced_dev=true uses equal-domain mean object CE, otherwise per-row object CE. class_domain_balanced_dev=true additionally gives each available label equal weight within each domain. Calibration only after weights frozen; fixed object/binary threshold grid .99,.995,.999,.9995,.9999; five input views must agree.",
        "object_gate": "Final >=50 accepted, zero false assertions, answerable recall>=.80, unknown recall>=.90; each positive class >=5 accepted and recall>=.80. Blank/shuffle image recall drop>=.15. Counts by source, not augmented views.",
        "retention_gate": "Each of seven old skills: final/transfer >=50 accepted, zero false assertions, recall>=.80, unknown recall>=.90, recall at most .02 below previous checkpoint on same fresh scenes.",
        "textbook_gate": "Only seven inspected non-blind diagnostics; never used for selection/tuning and never certify textbook mastery. Any accepted wrong diagnostic disallows object acceptance.",
        "limits": manifest["limits"],
        "training_admission": "Only this SHA-bound reviewed subset and fresh procedural replay; catalogue remains drafts, not blanket training admission.",
        "protected_mode": "When enabled: inherited tensors/old slices frozen, decay zero, old question-input vocabulary normalization/policy retained. Appended word/answer/intent rows and optional question-gated pixel residual train. One inherited causal core, no separate answer model.",
        "object_unknown_adapter": "When enabled, a zero-initialized linear correction to the inherited UNKNOWN logit learns from the same causal-core hidden state for supported object questions only. Object-question output vocabulary is eight admitted names plus UNKNOWN; legacy output vocabulary unchanged. No source/gold routing or lowered safety threshold.",
        "object_readout_adapter": "Optional zero-initialized learned residual from whole-frame visual mean/max and the shared causal READ state into the same vocabulary head; supported object questions only. No external pretrained weights, class prototypes or metadata inputs; legacy rows bypass it.",
        "background_augmentation": "Train-only intact full-frame zoom-out onto varied padding canvas. No foreground segmentation or changes to photographed scene background; transformations are not independent source evidence.",
        "evaluation_reuse": args.evaluation_note,
        "development_only": args.development_only,
        "selection_receipt_sha256": sha(args.selection_receipt)
        if args.selection_receipt
        else None,
    }
    write(args.output / "protocol.json", protocol)
    source_checkpoint = torch.load(args.previous, map_location="cpu", weights_only=True)
    width = source_checkpoint["width"]
    model = obj.ObjectsModel(
        width=width,
        vision_extension_channels=args.vision_extension_channels,
        vision_extension_depth=args.vision_extension_depth,
        object_unknown_adapter=args.object_unknown_adapter,
        vision_global_context=args.vision_global_context,
        object_readout_adapter=args.object_readout_adapter,
    )
    model.load_previous(source_checkpoint["model"])
    model.compatible_legacy_vocabulary = args.protect_inherited
    if args.warm_start:
        warm = obj.ObjectsModel.from_checkpoint(
            torch.load(args.warm_start, map_location="cpu", weights_only=True)
        )
        verify_inherited(warm, source_checkpoint["model"])
        model.load_object_warm_start(
            torch.load(args.warm_start, map_location="cpu", weights_only=True)
        )
    if args.protect_inherited:
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(
                name
                in {
                    "core.token_embedding.weight",
                    "core.lm_head.weight",
                    "question_intent.weight",
                    "question_intent.bias",
                }
                or name.startswith(
                    (
                        "vision_extension.",
                        "vision_global_context.",
                        "object_unknown_adapter.",
                        "object_readout_adapter.",
                    )
                )
            )
        model.core.token_embedding.weight.register_hook(
            lambda gradient: torch.cat(
                (
                    torch.zeros_like(gradient[: old.VOCAB_SIZE]),
                    gradient[old.VOCAB_SIZE :],
                )
            )
        )
        model.core.lm_head.weight.register_hook(
            lambda gradient: torch.cat(
                (
                    torch.zeros_like(gradient[: old.VOCAB_SIZE]),
                    gradient[old.VOCAB_SIZE :],
                )
            )
        )
        model.question_intent.weight.register_hook(
            lambda gradient: torch.cat((torch.zeros_like(gradient[:7]), gradient[7:]))
        )
        model.question_intent.bias.register_hook(
            lambda gradient: torch.cat((torch.zeros_like(gradient[:7]), gradient[7:]))
        )
    model.to(device)
    teacher = old.RelationsModel(width=width).to(device).eval()
    teacher.load_state_dict(source_checkpoint["model"])
    old_thresholds = json.loads(args.previous_policy.read_text())["thresholds"]
    replay = old.corpus(
        train_scenes=args.train_scenes,
        holdout_scenes=args.holdout_scenes,
        round_id=args.round_id,
        legacy_all_aliases=True,
    )
    write(args.output / "replay-split-audit.json", old.audit_splits(replay))
    archive = np.load(args.data / "pixels.npz", allow_pickle=False)
    owners = {}
    for split, records in manifest["records"].items():
        split_pixels = archive[split + "_pixels"]
        if archive[split + "_ids"].tolist() != [row["source_id"] for row in records]:
            raise ValueError("Source IDs not aligned with dataset provenance")
        if archive[split + "_answers"].tolist() != [row["answer"] for row in records]:
            raise ValueError("Labels not aligned with dataset provenance")
        for index, row in enumerate(records):
            if row["role"] == "SHARED_CONSTANT_CONTROL":
                if row["answer"] != "UNKNOWN" or split_pixels[index].any():
                    raise ValueError("Invalid shared absence control")
                continue
            pixel_sha = hashlib.sha256(split_pixels[index].tobytes()).hexdigest()
            if pixel_sha != row["pixel_sha256"]:
                raise ValueError("Pixel provenance mismatch")
            for identity in (row["source_id"], row["family_id"], pixel_sha):
                if owners.setdefault(identity, split) != split:
                    raise ValueError("Dataset family/source/pixel leakage")
    train_new, dev_new = (
        ObjectPrepared(archive, name, device) for name in ("train", "dev")
    )
    train_old, dev_old = (
        OldPrepared(replay[name], device) for name in ("train", "dev")
    )
    soft_targets = torch.zeros(len(train_old.answers), obj.VOCAB_SIZE, device=device)
    eligible = torch.zeros(len(train_old.answers), dtype=torch.bool, device=device)
    with torch.no_grad():
        for start in range(0, len(train_old.answers), 128):
            ids = torch.arange(
                start, min(start + 128, len(train_old.answers)), device=device
            )
            pixels, words, gold = train_old.batch(ids)
            p = teacher(pixels, words).softmax(-1)
            soft_targets[ids, : old.VOCAB_SIZE] = p
            eligible[ids] = (p.argmax(-1) == gold) & (p.max(-1).values >= 0.98)
    write(
        args.output / "replay-teacher-audit.json",
        {
            "eligible": int(eligible.sum()),
            "train_only": True,
            "new_object_pseudolabels": 0,
            "previous_sha256": PREVIOUS_SHA,
        },
    )
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=args.learning_rate,
        weight_decay=0 if args.protect_inherited else 0.01,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.steps, eta_min=args.learning_rate * 0.1
    )
    color_ids = torch.nonzero(train_old.intents == old.TASKS.index("color")).flatten()
    new_by_label = [
        torch.nonzero(train_new.answers == v).flatten()
        for v in (*obj.OBJECT_IDS.values(), obj.UNKNOWN)
    ]
    illustration_mask = torch.tensor(
        [
            row["role"]
            in (
                "VISUALLY_CURATED_NONBLIND_COLOR_ILLUSTRATION",
                "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH",
            )
            for row in manifest["records"]["train"]
        ],
        device=device,
    )
    illustration_by_label = [
        torch.nonzero((train_new.answers == v) & illustration_mask).flatten()
        for v in (*obj.OBJECT_IDS.values(), obj.UNKNOWN)
    ]
    if args.illustration_fraction and any(
        not len(ids) for ids in illustration_by_label
    ):
        raise ValueError(
            "Illustration-balanced replay requires all eight names and UNKNOWN"
        )
    history, best = [], float("inf")
    started = time.monotonic()
    for step in range(1, args.steps + 1):
        model.train()
        old_ids = torch.randint(len(train_old.answers), (32,), device=device)
        old_ids[:8] = color_ids[torch.randint(len(color_ids), (8,), device=device)]
        # Balanced admitted concepts, not source-category IDs entering forward.
        choices = torch.randint(len(new_by_label), (32,), device=device).cpu().tolist()
        new_ids = torch.tensor(
            [
                int(
                    (
                        pool := illustration_by_label[i]
                        if args.illustration_fraction
                        and torch.rand(()).item() < args.illustration_fraction
                        else new_by_label[i]
                    )[torch.randint(len(pool), ())]
                )
                for i in choices
            ],
            device=device,
        )
        old_images, old_words, old_labels = train_old.batch(old_ids)
        new_images, new_words, new_labels = train_new.batch(new_ids)
        # Preserve outline semantics; no fabricated object/count labels.
        new_images = (
            diverse_view(new_images)
            if args.diversity_augmentation
            else brightness_view(new_images)
        )
        if args.background_augmentation:
            new_images = background_view(new_images)
        images = torch.cat((new_images, old_images))
        words = torch.cat((new_words, old_words))
        labels = torch.cat((new_labels, old_labels))
        intents = torch.cat(
            (
                torch.full((32,), 7, device=device, dtype=torch.long),
                train_old.intents[old_ids],
            )
        )
        if torch.rand(()).item() < 0.5:
            images = translated_view(images, 1, 1)
        if torch.rand(()).item() < 0.5:
            images = images.flip(-1)
            words = old.mirror_questions(words)
        optimizer.zero_grad(set_to_none=True)
        logits, intent_logits = model(images, words, return_intent=True)
        loss = F.cross_entropy(logits, labels) + 0.2 * F.cross_entropy(
            intent_logits, intents
        )
        keep = eligible[old_ids]
        if keep.any() and not args.protect_inherited:
            loss = loss + F.kl_div(
                F.log_softmax(logits[32:][keep], -1),
                soft_targets[old_ids[keep]],
                reduction="batchmean",
            )
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
        optimizer.step()
        scheduler.step()
        if step % args.eval_every == 0 or step == args.steps:
            new_probs = probabilities(model, dev_new, consensus=False)
            old_probs = probabilities(model, dev_old, consensus=False)
            new_loss = (
                domain_balanced_loss(
                    dev_new,
                    new_probs,
                    manifest["records"]["dev"],
                    class_balanced=args.class_domain_balanced_dev,
                )
                if args.domain_balanced_dev
                else loss_on(dev_new, new_probs)
            )
            score = 0.5 * new_loss + 0.5 * loss_on(dev_old, old_probs)
            record = {
                "step": step,
                "dev_loss": score,
                "object_dev": summary(dev_new, new_probs, dict.fromkeys(obj.TASKS, 0))[
                    "all"
                ],
                "seconds": time.monotonic() - started,
            }
            history.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if score < best:
                best = score
                torch.save(
                    {
                        "model": model.state_dict(),
                        "width": width,
                        "layers": model.core.config.num_layers,
                        "architecture": model.vision_extension_config,
                        "step": step,
                        "previous_sha256": PREVIOUS_SHA,
                        "compatible_legacy_vocabulary": args.protect_inherited,
                    },
                    args.output / "best.pt",
                )
    if args.evaluate_checkpoint:
        shutil.copyfile(args.evaluate_checkpoint, args.output / "best.pt")
    chosen = torch.load(args.output / "best.pt", map_location=device, weights_only=True)
    if (
        chosen.get("architecture", {}) != model.vision_extension_config
        or chosen.get("compatible_legacy_vocabulary") is not args.protect_inherited
    ):
        raise ValueError("Checkpoint architecture/normalizer mismatch")
    model.load_state_dict(chosen["model"])
    if args.protect_inherited:
        verify_inherited(model, source_checkpoint["model"])
    verify_inputs(args, protocol)
    if args.development_only:
        write(
            args.output / "development-report.json",
            {
                "schema": 1,
                "status": "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL",
                "history": history,
                "best_step": chosen["step"],
                "best_dev_loss": best,
                "architecture": model.vision_extension_config,
                "inherited_tensors_byte_preserved": args.protect_inherited,
                "parameters": sum(p.numel() for p in model.parameters()),
                "trainable_parameters": sum(
                    p.numel() for p in model.parameters() if p.requires_grad
                ),
                "trainable_parameter_count_note": "Whole trainable tensors counted; old embedding/head/intent slices are additionally frozen by gradient hooks and verified byte-identical.",
                "checkpoint_sha256": sha(args.output / "best.pt"),
                "protocol_sha256": sha(args.output / "protocol.json"),
                "dataset_sha256": protocol["dataset_sha256"],
                "production_admitted": False,
                "elapsed_seconds": time.monotonic() - started,
                "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated()
                if device.type == "cuda"
                else None,
                "limits": "Selection uses development data only. No calibration thresholds, final, regression, or textbook predictions are produced.",
            },
        )
        return
    calibration_new = ObjectPrepared(archive, "calibration", device)
    calibration_old = OldPrepared(replay["calibration"], device)
    new_probs = probabilities(model, calibration_new)
    old_probs = probabilities(model, calibration_old)
    thresholds = obj.calibrate(
        tasks(calibration_new) + tasks(calibration_old),
        calibration_new.answers.cpu().tolist() + calibration_old.answers.cpu().tolist(),
        new_probs + old_probs,
    )
    if args.protect_inherited:
        # Old parameters AND full old normalization are unchanged; use the exact
        # accepted old policy, not a lower support recalibration of that policy.
        thresholds.update(old_thresholds)
        verify_inherited(model, source_checkpoint["model"])
    checkpoint_sha = sha(args.output / "best.pt")
    write(
        args.output / "frozen-calibration.json",
        {
            "thresholds": thresholds,
            "checkpoint_sha256": checkpoint_sha,
            "protocol_sha256": sha(args.output / "protocol.json"),
        },
    )
    report = {
        "schema": 1,
        "previous_sha256": PREVIOUS_SHA,
        "checkpoint_sha256": checkpoint_sha,
        "protocol_sha256": sha(args.output / "protocol.json"),
        "dataset_sha256": protocol["dataset_sha256"],
        "history": history,
        "best_step": chosen["step"],
        "thresholds": thresholds,
        "parameters": sum(p.numel() for p in model.parameters()),
        "architecture": model.vision_extension_config,
        "inherited_tensors_byte_preserved": args.protect_inherited,
        "selection_receipt_sha256": protocol["selection_receipt_sha256"],
        "calibration": summary(calibration_new, new_probs, thresholds),
        "tests": {},
        "limits": protocol["limits"],
        "training_started": True,
        "production_admitted": False,
    }

    def evaluate(name, data, mode="normal"):
        p = probabilities(model, data, mode=mode)
        stats = summary(data, p, thresholds)
        ids = (
            data.ids
            if isinstance(data, ObjectPrepared)
            else [row.scene.scene_id for row in data.rows]
        )
        write(
            args.output / (name + "-predictions.json"),
            [
                {
                    "source_id": identifier,
                    "task": task,
                    "gold": obj.ANSWER_TEXT[gold],
                    "selected": obj.ANSWER_TEXT[prediction],
                    "probabilities": values,
                }
                for identifier, task, gold, prediction, values in zip(
                    ids,
                    tasks(data),
                    data.answers.cpu().tolist(),
                    selected(data, p, thresholds),
                    p,
                    strict=True,
                )
            ],
        )
        return stats

    final_new = ObjectPrepared(archive, "final", device)
    report["tests"]["object_final"] = evaluate("object-final", final_new)
    for mode in ("blank", "shuffled"):
        report["tests"]["object_" + mode] = evaluate(
            "object-" + mode, final_new, mode=mode
        )
    regression_gate = True
    if "regression" in manifest["records"]:
        report["tests"]["object_regression"] = evaluate(
            "object-regression", ObjectPrepared(archive, "regression", device)
        )
        rstats = report["tests"]["object_regression"]["all"]
        regression_gate = (
            rstats["false_assertions"] == 0
            and (rstats["answerable_recall"] or 0) >= 0.8
            and (rstats["unknown_recall"] or 0) >= 0.9
        )
    report["tests"]["textbook_diagnostic"] = evaluate(
        "textbook-diagnostic", ObjectPrepared(archive, "textbook_diagnostic", device)
    )
    retention = {}
    for split in ("final", "transfer"):
        data = OldPrepared(replay[split], device)
        report["tests"]["legacy_" + split] = evaluate("legacy-" + split, data)
        baseline = old_summarize(
            data.rows, old_probabilities(teacher, data, consensus=True), old_thresholds
        )
        report["tests"]["previous_baseline_" + split] = baseline
        for task in old.TASKS:
            stats = report["tests"]["legacy_" + split][task]
            retention[task] = (
                retention.get(task, True)
                and stats["accepted"] >= 50
                and stats["false_assertions"] == 0
                and (stats["answerable_recall"] or 0) >= 0.80
                and (stats["unknown_recall"] or 0) >= 0.90
                and (stats["answerable_recall"] or 0)
                >= (baseline[task]["answerable_recall"] or 0) - 0.02
            )
    stats = report["tests"]["object_final"]["all"]
    object_gate = (
        stats["accepted"] >= 50
        and stats["false_assertions"] == 0
        and (stats["answerable_recall"] or 0) >= 0.80
        and (stats["unknown_recall"] or 0) >= 0.90
    )
    object_gate = (
        object_gate
        and len(report["tests"]["object_final"]["by_concept"]) == 8
        and all(
            v["accepted"] >= 5 and (v["answerable_recall"] or 0) >= 0.80
            for v in report["tests"]["object_final"]["by_concept"].values()
        )
    )
    for mode in ("blank", "shuffled"):
        object_gate = (
            object_gate
            and (stats["answerable_recall"] or 0)
            - (report["tests"]["object_" + mode]["all"]["answerable_recall"] or 0)
            >= 0.15
        )
    object_gate = (
        object_gate
        and report["tests"]["textbook_diagnostic"]["all"]["false_assertions"] == 0
    )
    report.update(
        {
            "object_gate": bool(object_gate),
            "retention_gates": {k: bool(v) for k, v in retention.items()},
            "regression_gate": bool(regression_gate),
            "status": "BOUNDED_OBJECT_GATE_PASSED_NOT_PRODUCTION"
            if object_gate and all(retention.values()) and regression_gate
            else "REJECTED_NOT_PRODUCTION",
            "elapsed_seconds": time.monotonic() - started,
            "torch": torch.__version__,
            "device": str(device),
            "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated()
            if device.type == "cuda"
            else None,
            "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved()
            if device.type == "cuda"
            else None,
        }
    )
    write(args.output / "report.json", report)
    verify_inputs(args, protocol)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "object_gate",
                    "retention_gates",
                    "thresholds",
                    "elapsed_seconds",
                    "peak_cuda_allocated_bytes",
                )
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

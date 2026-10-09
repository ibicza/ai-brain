"""Bounded two-schedule own-weight composition experiment; never activates weights."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_brain.training import primary_composition as course
from ai_brain.training import primary_objects as old
from ai_brain.training import primary_relations as relations
from ai_brain.training import primary_zero as base


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class Prepared:
    def __init__(self, data, device):
        self.data = data
        self.pixels = (
            torch.from_numpy(data["pixels"]).permute(0, 3, 1, 2).float().to(device)
            / 255
        )
        self.questions = torch.from_numpy(data["questions"]).to(device)
        self.labels = torch.from_numpy(data["labels"]).to(device)
        self.image_index = torch.from_numpy(data["image_index"]).to(device)

    def batch(self, indices):
        return (
            self.pixels[self.image_index[indices]],
            self.questions[indices],
            self.labels[indices],
        )


@torch.no_grad()
def probabilities(model, prepared, batch=96, ablation=None):
    model.eval()
    result = []
    for start in range(0, len(prepared.labels), batch):
        x, q, _ = prepared.batch(
            torch.arange(
                start,
                min(start + batch, len(prepared.labels)),
                device=prepared.labels.device,
            )
        )
        if ablation == "blank":
            x = torch.full_like(x, 0.5)
        result.append(model(x, q).softmax(-1).cpu().numpy())
    return np.concatenate(result)


def balanced_loss(prepared, p):
    losses = -np.log(np.maximum(p[np.arange(len(p)), prepared.data["labels"]], 1e-12))
    groups = {}
    for i, r in enumerate(prepared.data["records"]):
        groups.setdefault((r["task"], r["answer"]), []).append(losses[i])
    return float(np.mean([np.mean(v) for v in groups.values()]))


def evaluate(prepared, p, thresholds):
    records = prepared.data["records"]
    predictions = course.select(p, [thresholds[r["task"]] for r in records])
    gold = prepared.data["labels"].tolist()
    tasks = {}
    for task in course.VALUES:
        indices = [i for i, r in enumerate(records) if r["task"] == task]
        tasks[task] = course.statistics(
            [gold[i] for i in indices], [predictions[i] for i in indices]
        )
    complete = []
    for i in range(0, len(gold), 3):
        if all(g != course.UNKNOWN for g in gold[i : i + 3]):
            complete.append(predictions[i : i + 3] == gold[i : i + 3])
    # Same image, opposite targets: cannot pass by assigning all scene attributes to both objects.
    binding = {}
    for task in course.VALUES:
        pairs = []
        offset = list(course.VALUES).index(task)
        for i in range(0, len(gold), 6):
            a, b = i + offset, i + 3 + offset
            if gold[a] != gold[b] and course.UNKNOWN not in (gold[a], gold[b]):
                pairs.append(predictions[a] == gold[a] and predictions[b] == gold[b])
        binding[task] = {
            "eligible_scene_pairs": len(pairs),
            "both_correct_rate": sum(pairs) / len(pairs) if pairs else None,
        }
    return {
        "overall": course.statistics(gold, predictions),
        "tasks": tasks,
        "complete_visible_descriptions": {
            "eligible_objects": len(complete),
            "all_three_correct_rate": sum(complete) / len(complete)
            if complete
            else None,
        },
        "target_binding": binding,
        "predictions": predictions,
    }


def calibrate(prepared, p, min_accepted=40):
    thresholds, report = {}, {}
    for task in course.VALUES:
        indices = [
            i for i, r in enumerate(prepared.data["records"]) if r["task"] == task
        ]
        pp = p[indices]
        gold = prepared.data["labels"][indices].tolist()
        choices = []
        for threshold in (0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 0.9999):
            metrics = course.statistics(gold, course.select(pp, [threshold] * len(pp)))
            if metrics["false_assertions"] == 0 and metrics["accepted"] >= min_accepted:
                choices.append((metrics["accepted"], threshold, metrics))
        best = max(choices, key=lambda v: (v[0], v[1])) if choices else None
        thresholds[task] = best[1] if best else None
        report[task] = {
            "threshold": thresholds[task],
            "metrics": best[2]
            if best
            else course.statistics(gold, [course.UNKNOWN] * len(gold)),
        }
    return thresholds, {
        "selection_split": "calibration_only",
        "minimum_accepted_per_task": min_accepted,
        "allowed_observed_calibration_errors": 0,
        "tasks": report,
        "limits": "Experimental risk/coverage policy, not a guarantee on new images. Correlated questions/views are not independent sources.",
    }


def verify_inherited(model, state):
    if set(model.inherited.state_dict()) != set(state) or any(
        not torch.equal(model.inherited.state_dict()[k].cpu(), v)
        for k, v in state.items()
    ):
        raise ValueError("Inherited tensor changed")


@torch.no_grad()
def legacy_check(model, device):
    rows = relations.corpus(train_scenes=24, holdout_scenes=24, round_id=11031)["dev"]
    by_task = {task: [] for task in relations.TASKS}
    for row in rows:
        if len(by_task[row.task]) < 6:
            by_task[row.task].append(row)
    results = {}
    for task, group in by_task.items():
        images = (
            torch.from_numpy(np.stack([base.render(r.scene)[0] for r in group]))
            .permute(0, 3, 1, 2)
            .float()
            .to(device)
        )
        # Existing base renderer returns [0,1] floats.
        questions = torch.tensor(
            [old.encode_question(r.question) for r in group], device=device
        )
        before = model.inherited(images, questions)
        after = model.legacy_forward(images, questions)
        if not torch.equal(before, after):
            raise ValueError("Legacy numerical behavior changed")
        results[task] = {"examples": len(group), "logits_exact_equal": True}
    return {
        "tasks": results,
        "limits": "Exact delegated legacy-forward and inherited tensor checks; not a new seven-skill acceptance exam.",
    }


def run(args):
    root = args.output.resolve()
    if root.exists():
        raise ValueError("Fresh experiment directory required")
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("Requested CUDA unavailable")
    device = torch.device(args.device)
    warm_sha = sha(args.previous)
    previous = torch.load(args.previous, map_location="cpu", weights_only=True)
    inherited_state = {
        k: v.detach().cpu().clone() for k, v in previous["model"].items()
    }
    model = course.CompositionModel(old.ObjectsModel.from_checkpoint(previous)).to(
        device
    )
    initial = model.candidate_state()
    root.mkdir(parents=True)
    protocol = {
        "schema": 1,
        "source_capsule_sha256": os.environ.get("AI_BRAIN_CAPSULE_SHA256"),
        "previous_sha256": warm_sha,
        "seed": args.seed,
        "steps_per_schedule": args.steps,
        "batch_size": 64,
        "learning_rate": 0.001,
        "schedules": ["joint", "curriculum"],
        "selection": "Lowest balanced dev CE only. Calibration and three final cohorts accessed after candidate freeze.",
        "held_combinations": sorted(course.HELD_COMBINATIONS),
        "scope": "Procedural two-object color/shape/pattern + bounded RU/EN queries. No animal names, anatomy, photographs, textbooks or free-form text learned.",
        "production_admitted": False,
        "attribute_attention": model.attribute_attention_enabled,
        "literature": [
            "https://proceedings.mlr.press/v119/koh20a.html",
            "https://arxiv.org/abs/1904.12584",
            "https://arxiv.org/abs/2210.01936",
        ],
        "adaptation": "Shared own causal core, attribute supervision, explicit target binding and curriculum comparison. Not reproduction of CBM/NS-CL architectures.",
        "capacity": {
            "inherited_parameters": sum(
                p.numel() for p in model.inherited.parameters()
            ),
            "new_trainable_parameters": sum(
                p.numel() for p in model.parameters() if p.requires_grad
            ),
        },
    }
    write(root / "protocol.json", protocol)
    raw = {
        split: course.prepare(
            course.scenes(
                split,
                args.train_images if split == "train" else args.holdout_images,
                args.seed * 100000 + offset * 10000,
            )
        )
        for offset, split in enumerate(
            ("train", "dev", "calibration", "final", "combinations", "transfer")
        )
    }
    write(root / "split-audit.json", course.audit(raw))
    arrays = {}
    for split, group in raw.items():
        for key in ("pixels", "questions", "labels", "image_index"):
            arrays[split + "_" + key] = group[key]
    np.savez_compressed(root / "dataset.npz", **arrays)
    with gzip.open(root / "dataset-records.json.gz", "wt", encoding="utf-8") as f:
        json.dump(
            {
                k: {"records": v["records"], "scenes": v["scenes"]}
                for k, v in raw.items()
            },
            f,
            ensure_ascii=False,
        )
    Image = __import__("PIL.Image", fromlist=["Image"])
    sheet = Image.new("RGB", (96 * 8, 96 * 4))
    for i, image in enumerate(raw["train"]["pixels"][:32]):
        sheet.paste(Image.fromarray(image), (i % 8 * 96, i // 8 * 96))
    sheet.save(root / "actual-input-contact-sheet.png")
    train, dev = Prepared(raw["train"], device), Prepared(raw["dev"], device)
    train_tasks = np.asarray([r["task"] for r in raw["train"]["records"]])
    trials = []
    for schedule in ("joint", "curriculum"):
        torch.manual_seed(args.seed + 1)
        model.load_candidate(initial)
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad],
            lr=0.001,
            weight_decay=0.0001,
        )
        rng = np.random.default_rng(args.seed + 2)
        best_loss = float("inf")
        trial = root / schedule
        trial.mkdir()
        history = []
        started = time.monotonic()
        for step in range(1, args.steps + 1):
            model.train()
            # First third: simpler color/shape; later all three attributes.
            pool = (
                np.flatnonzero(train_tasks != "pattern")
                if schedule == "curriculum" and step <= args.steps // 3
                else np.arange(len(train.labels))
            )
            indices = torch.tensor(rng.choice(pool, size=64), device=device)
            x, q, y = train.batch(indices)
            optimizer.param_groups[0]["lr"] = 0.001 * (
                0.2 + 0.8 * 0.5 * (1 + math.cos(math.pi * step / args.steps))
            )
            optimizer.zero_grad(set_to_none=True)
            loss = F.cross_entropy(model(x, q), y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0
            )
            optimizer.step()
            if step % args.eval_every == 0 or step == args.steps:
                p = probabilities(model, dev)
                score = balanced_loss(dev, p)
                verify_inherited(model, inherited_state)
                point = {
                    "step": step,
                    "train_loss": float(loss.detach()),
                    "balanced_dev_ce": score,
                    "elapsed_seconds": time.monotonic() - started,
                }
                history.append(point)
                if score < best_loss:
                    best_loss = score
                    torch.save(
                        {
                            "schema": 1,
                            "candidate": model.candidate_state(),
                            "previous_sha256": warm_sha,
                            "width": previous["width"],
                            "layers": previous.get("layers", 2),
                            "answers": course.ANSWERS,
                            "new_words": course.NEW_WORDS,
                            "step": step,
                            "schedule": schedule,
                            "attribute_attention": model.attribute_attention_enabled,
                        },
                        trial / "best.pt",
                    )
                write(trial / "history.json", history)
                print(json.dumps({"schedule": schedule, **point}), flush=True)
        trials.append(
            {
                "schedule": schedule,
                "best_dev_ce": best_loss,
                "checkpoint": str(trial / "best.pt"),
                "checkpoint_sha256": sha(trial / "best.pt"),
                "history": history,
            }
        )
    winner = min(trials, key=lambda r: r["best_dev_ce"])
    write(
        root / "candidate-freeze.json",
        {
            "winner": winner,
            "trials": trials,
            "dataset_sha256": sha(root / "dataset.npz"),
            "records_sha256": sha(root / "dataset-records.json.gz"),
            "protocol_sha256": sha(root / "protocol.json"),
            "production_admitted": False,
            "final_evaluation_started": False,
        },
    )
    selected = torch.load(winner["checkpoint"], map_location="cpu", weights_only=True)
    model.load_candidate(selected["candidate"])
    verify_inherited(model, inherited_state)
    model.eval()
    calibration = Prepared(raw["calibration"], device)
    thresholds, policy = calibrate(calibration, probabilities(model, calibration))
    write(root / "policy-frozen.json", policy)
    reports = {}
    for split in ("dev", "final", "combinations", "transfer"):
        group = dev if split == "dev" else Prepared(raw[split], device)
        p = probabilities(model, group)
        raw_eval = evaluate(group, p, {task: 0 for task in course.VALUES})
        safe_eval = evaluate(group, p, thresholds)
        report = {
            "raw_argmax": {k: v for k, v in raw_eval.items() if k != "predictions"},
            "selected": {k: v for k, v in safe_eval.items() if k != "predictions"},
            "image_count": len(group.pixels),
            "independence": "Same renderer family, unseen seeds. Not an independent blind external-source exam.",
        }
        reports[split] = report
        write(root / (split + "-results.json"), report)
        with gzip.open(
            root / (split + "-predictions.json.gz"), "wt", encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "records": group.data["records"],
                    "probabilities": p.tolist(),
                    "selected": safe_eval["predictions"],
                    "raw_predictions": raw_eval["predictions"],
                },
                f,
                ensure_ascii=False,
            )
        if split == "final":
            blank = evaluate(
                group, probabilities(model, group, ablation="blank"), thresholds
            )
            write(
                root / "blank-image-ablation.json",
                {k: v for k, v in blank.items() if k != "predictions"},
            )
            examples = []
            for i in range(0, min(len(p), 72), 6):
                examples.append(
                    {
                        "scene_id": group.data["records"][i]["scene_id"],
                        "description": course.describe(
                            safe_eval["predictions"][i : i + 6]
                        ),
                        "gold": [
                            course.ANSWERS[y] for y in group.data["labels"][i : i + 6]
                        ],
                    }
                )
            write(root / "description-examples.json", examples)
    retention = legacy_check(model, device)
    verify_inherited(model, inherited_state)
    if (
        sha(args.previous) != warm_sha
        or sha(winner["checkpoint"]) != winner["checkpoint_sha256"]
    ):
        raise ValueError("Source or frozen checkpoint changed")
    passed = all(
        all(
            task["false_assertions"] == 0
            and task["answerable_recall"] >= 0.8
            and task["unknown_recall"] >= 0.9
            for task in reports[split]["selected"]["tasks"].values()
        )
        for split in ("final", "combinations", "transfer")
    )
    result = {
        "schema": 1,
        "status": "BOUNDED_SYNTHETIC_SCREEN_PASSED"
        if passed
        else "NEEDS_WORK_NOT_PRODUCTION",
        "production_admitted": False,
        "scope": protocol["scope"],
        "winner": winner["schedule"],
        "checkpoint_sha256": winner["checkpoint_sha256"],
        "inherited_checkpoint_sha256": warm_sha,
        "inherited_tensors_byte_preserved": True,
        "legacy_retention": retention,
        "reports": reports,
        "new_word_tokens": course.NEW_WORDS,
        "capacity": protocol["capacity"],
        "thresholds": thresholds,
        "limits": "No claim that these procedural attributes transfer to photographs, giraffes, watermelons or textbooks. Language is closed RU/EN queries, not a generative language model. Successful stage is not production admission.",
    }
    write(root / "result.json", result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "winner": result["winner"],
                "checkpoint_sha256": result["checkpoint_sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--steps", type=int, default=1800)
    parser.add_argument("--eval-every", type=int, default=150)
    parser.add_argument("--train-images", type=int, default=1200)
    parser.add_argument("--holdout-images", type=int, default=240)
    parser.add_argument("--seed", type=int, default=11031)
    args = parser.parse_args()
    if min(args.steps, args.eval_every, args.train_images, args.holdout_images) < 1:
        parser.error("Positive experiment sizes required")
    run(args)

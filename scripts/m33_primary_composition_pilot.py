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
from ai_brain.training import primary_composition_controls as controls
from ai_brain.training import primary_composition_views as views
from ai_brain.training import primary_objects as old
from ai_brain.training import primary_relations as relations
from ai_brain.training import primary_zero as base

CALIBRATION_RULES = ("maximum_coverage", "coverage_guarded_strict")
STRICT_COHORT_CONSTRAINTS = {
    "minimum_answerable_recall": 0.8,
    "minimum_unknown_recall": 0.9,
}


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


def join_data(left, right):
    """Join sealed calibration sources without losing image/target correspondence."""
    return {
        "pixels": np.concatenate((left["pixels"], right["pixels"])),
        "questions": np.concatenate((left["questions"], right["questions"])),
        "labels": np.concatenate((left["labels"], right["labels"])),
        "image_index": np.concatenate(
            (left["image_index"], right["image_index"] + len(left["pixels"]))
        ),
        "records": left["records"] + right["records"],
        "scenes": left["scenes"] + right["scenes"],
    }


def consistency_loss(first, second):
    """Two-view JS with zero probability for masked, unsupported answer classes."""
    if first.shape != second.shape or first.ndim != 2:
        raise ValueError("Consistent answer spaces required")
    p, q = first.softmax(-1), second.softmax(-1)
    if not torch.isfinite(p).all() or not torch.isfinite(q).all():
        raise ValueError("Invalid consistency logits")
    if not torch.equal(torch.isfinite(first), torch.isfinite(second)):
        raise ValueError("View changed supported answer scope")
    m = (p + q) / 2
    logm = m.clamp_min(1e-12).log()
    return (
        0.5 * (p * (p.clamp_min(1e-12).log() - logm)).sum(-1)
        + 0.5 * (q * (q.clamp_min(1e-12).log() - logm)).sum(-1)
    ).mean()


def masked_smoothing_loss(logits, labels, amount):
    """Smooth only supported answers; masked -inf must not enter the average."""
    if (
        type(amount) not in (float, int)
        or not math.isfinite(amount)
        or not 0 <= amount <= 0.2
    ):
        raise ValueError("Invalid bounded smoothing")
    if not torch.isfinite(
        logits[torch.arange(len(labels), device=labels.device), labels]
    ).all():
        raise ValueError("Training label outside supported answers")
    ordinary = F.cross_entropy(logits, labels)
    if amount == 0:
        return ordinary
    allowed = torch.isfinite(logits)
    logp = logits.log_softmax(-1).masked_fill(~allowed, 0)
    smooth = -(logp.sum(-1) / allowed.sum(-1)).mean()
    return (1 - amount) * ordinary + amount * smooth


@torch.no_grad()
def probabilities(model, prepared, batch=96, ablation=None, *, single_view=False):
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
        if getattr(model, "reflection_consensus", False) and not single_view:
            p = views.consistent_probabilities(model, x, q)
        else:
            p = model(x, q).softmax(-1)
        result.append(p.cpu().numpy())
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


def calibrate(prepared, p, min_accepted=40, *, rule="maximum_coverage", cohorts=None):
    if (
        rule not in CALIBRATION_RULES
        or type(min_accepted) is not int
        or min_accepted < 1
    ):
        raise ValueError("Invalid calibration rule or support count")
    if rule == "coverage_guarded_strict" and (
        cohorts is None
        or not isinstance(cohorts, (list, tuple))
        or len(cohorts) != len(prepared.data["records"])
        or not cohorts
        or any(v not in ("native", "authored") for v in cohorts)
    ):
        raise ValueError("Explicit aligned calibration cohorts required")
    thresholds, report = {}, {}
    for task in course.VALUES:
        indices = [
            i for i, r in enumerate(prepared.data["records"]) if r["task"] == task
        ]
        pp = p[indices]
        gold = prepared.data["labels"][indices].tolist()
        group_indices = (
            {
                name: [j for j, i in enumerate(indices) if cohorts[i] == name]
                for name in sorted(set(cohorts))
            }
            if rule == "coverage_guarded_strict"
            else {}
        )
        choices = []
        for threshold in (0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 0.9999):
            predictions = course.select(pp, [threshold] * len(pp))
            metrics = course.statistics(gold, predictions)
            grouped = {
                name: course.statistics(
                    [gold[j] for j in js], [predictions[j] for j in js]
                )
                for name, js in group_indices.items()
            }
            recall_ok = all(
                (v["answerable_recall"] is None or v["answerable_recall"] >= 0.8)
                and (v["unknown_recall"] is None or v["unknown_recall"] >= 0.9)
                for v in grouped.values()
            )
            if (
                metrics["false_assertions"] == 0
                and metrics["accepted"] >= min_accepted
                and recall_ok
            ):
                choices.append((metrics["accepted"], threshold, metrics, grouped))
        best = (
            max(
                choices,
                key=lambda v: (
                    (v[1], v[0]) if rule == "coverage_guarded_strict" else (v[0], v[1])
                ),
            )
            if choices
            else None
        )
        thresholds[task] = best[1] if best else None
        report[task] = {
            "threshold": thresholds[task],
            "metrics": best[2]
            if best
            else course.statistics(gold, [course.UNKNOWN] * len(gold)),
        }
        if rule == "coverage_guarded_strict":
            report[task]["cohort_metrics"] = (
                best[3]
                if best
                else {
                    name: course.statistics(
                        [gold[j] for j in js], [course.UNKNOWN] * len(js)
                    )
                    for name, js in group_indices.items()
                }
            )
    return thresholds, {
        "selection_split": "calibration_only",
        "selection_rule": rule,
        "cohort_constraints": STRICT_COHORT_CONSTRAINTS
        if rule == "coverage_guarded_strict"
        else None,
        "cohort_names": sorted(set(cohorts))
        if rule == "coverage_guarded_strict"
        else [],
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
    if max(args.train_images, args.holdout_images) > 10000 or args.seed < 0:
        raise ValueError(
            "Scene counts must respect the disjoint 10,000-seed split spacing"
        )
    auxiliary_images = getattr(args, "auxiliary_images", 0)
    exposure_profile = getattr(args, "exposure_profile", "standard")
    if exposure_profile not in controls.EXPOSURE_PROFILES:
        raise ValueError("Invalid control exposure profile")
    calibration_rule = getattr(args, "calibration_rule", "maximum_coverage")
    if calibration_rule not in CALIBRATION_RULES:
        raise ValueError("Invalid calibration selection rule")
    consistency_amount = getattr(args, "consistency_loss", 0.0)
    if type(auxiliary_images) is not int or not 0 <= auxiliary_images <= 10000:
        raise ValueError("Bounded auxiliary scene count required")
    if (
        type(consistency_amount) not in (float, int)
        or not math.isfinite(consistency_amount)
        or not 0 <= consistency_amount <= 1
    ):
        raise ValueError("Invalid consistency strength")
    torch.set_num_threads(2)
    from ai_brain.training import primary_numeric_backend as numeric

    numeric_backend = numeric.configure(getattr(args, "numeric_precision", "legacy"))
    torch.manual_seed(args.seed)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("Requested CUDA unavailable")
    device = torch.device(args.device)
    warm_sha = sha(args.previous)
    previous = torch.load(args.previous, map_location="cpu", weights_only=True)
    inherited_state = {
        k: v.detach().cpu().clone() for k, v in previous["model"].items()
    }
    model = course.CompositionModel(
        old.ObjectsModel.from_checkpoint(previous),
        spatial_readout=args.spatial_readout,
        shape_edges=args.shape_edges,
    ).to(device)
    model.reflection_consensus = getattr(args, "reflection_consensus", False)
    candidate_anchor = None
    if args.warm_candidate is not None:
        candidate_anchor = sha(args.warm_candidate)
        warm = torch.load(args.warm_candidate, map_location="cpu", weights_only=True)
        if (
            warm["previous_sha256"] != warm_sha
            or tuple(warm["answers"]) != course.ANSWERS
            or warm["new_words"] != course.NEW_WORDS
            or warm["attribute_attention"] != model.attribute_attention_enabled
        ):
            raise ValueError("Incompatible own composition warm start")
        if warm.get("spatial_readout", False) and not model.spatial_readout_enabled:
            raise ValueError("Cannot remove a learned spatial readout")
        if warm.get("shape_edges", False) and not model.shape_edges_enabled:
            raise ValueError("Cannot silently remove the learned shape edge view")
        model.load_warm_candidate(warm["candidate"])
    initial = model.candidate_state()
    root.mkdir(parents=True)
    protocol = {
        "schema": 1,
        "source_capsule_sha256": os.environ.get("AI_BRAIN_CAPSULE_SHA256"),
        "previous_sha256": warm_sha,
        "candidate_anchor_sha256": candidate_anchor,
        "dataset_profile": args.dataset_profile,
        "background_rng_policy": course.BACKGROUND_RNG_POLICY
        if args.dataset_profile.endswith("background_clear")
        else None,
        "curve_rng_policy": course.RICH_CURVE_RNG_POLICY
        if args.dataset_profile
        in ("rich_curve_background_clear", "aspect_rich_curve_background_clear")
        else course.CURVE_RNG_POLICY
        if args.dataset_profile == "curve_background_clear"
        else None,
        "label_rng_policy": course.LABEL_RNG_POLICY,
        "aspect_rng_policy": course.ASPECT_RNG_POLICY
        if args.dataset_profile == "aspect_rich_curve_background_clear"
        else None,
        "independent_labels": True,
        "seed": args.seed,
        "numeric_backend": numeric_backend,
        "steps_per_schedule": args.steps,
        "batch_size": 64,
        "learning_rate": 0.001,
        "schedules": ["joint", "curriculum"],
        "selection": "Lowest balanced dev CE only; native/authored dev have equal weight when auxiliary data exists. Calibration and final cohorts accessed after candidate freeze.",
        "calibration_rule": calibration_rule,
        "calibration_constraints": STRICT_COHORT_CONSTRAINTS
        if calibration_rule == "coverage_guarded_strict"
        else None,
        "held_combinations": sorted(course.HELD_COMBINATIONS),
        "scope": "Procedural two-object color/shape/pattern + bounded RU/EN queries. No animal names, anatomy, photographs, textbooks or free-form text learned.",
        "production_admitted": False,
        "acceptance": {
            "task_positive_recall_min": 0.8,
            "task_unknown_recall_min": 0.9,
            "accepted_errors_max": 0,
            "complete_description_recall_min": 0.8,
            "both_targets_correct_min": 0.8,
            "blank_image_accepted_max": 0,
        },
        "attribute_attention": model.attribute_attention_enabled,
        "spatial_readout": model.spatial_readout_enabled,
        "shape_edges": model.shape_edges_enabled,
        "label_smoothing": args.label_smoothing,
        "reflection_consensus": model.reflection_consensus,
        "training_reflections": model.reflection_consensus,
        "auxiliary_images": auxiliary_images,
        "exposure_profile": exposure_profile,
        "exposure_shapes": controls.EXPOSURE_PROFILES[exposure_profile],
        "paper_rng_policy": controls.PAPER_RNG_POLICY
        if exposure_profile == "palette_paper_aspects"
        else None,
        "held_control_shapes": controls.HELD_OUT_SHAPES,
        "auxiliary_calibration": auxiliary_images > 0,
        "held_control_final": auxiliary_images > 0,
        "consistency_loss": consistency_amount,
        "score_semantics": "Four-view unanimity, minimum confidence; disagreement UNKNOWN. Not calibrated probability. Raw argmax is after this fixed view policy."
        if model.reflection_consensus
        else "Single-view softmax",
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
    from ai_brain.training import primary_composition_rng_audit as rng_audit

    leakage_audit = rng_audit.audit(
        seed=args.seed * 100000 + 100000, profile=args.dataset_profile
    )
    write(root / "rng-independence-audit.json", leakage_audit)
    if not leakage_audit["known_shortcut_absent"]:
        raise ValueError("Background/label RNG leakage detected before training")
    raw = {
        split: course.prepare(
            course.scenes(
                split,
                args.train_images if split == "train" else args.holdout_images,
                args.seed * 100000 + offset * 10000,
                profile=args.dataset_profile,
                independent_labels=True,
            )
        )
        for offset, split in enumerate(
            ("train", "dev", "calibration", "final", "combinations", "transfer")
        )
    }
    write(root / "split-audit.json", course.audit(raw))
    if auxiliary_images:
        auxiliary = {
            split: controls.prepare(
                controls.scenes(
                    "held_control" if split == "control_final" else "exposure",
                    auxiliary_images if split == "exposure" else args.holdout_images,
                    args.seed * 100000 + (6 + offset) * 10000,
                    cohort=split,
                    exposure_profile=exposure_profile,
                )
            )
            for offset, split in enumerate(
                ("exposure", "control_calibration", "control_final")
            )
        }
        auxiliary["control_dev"] = controls.prepare(
            controls.scenes(
                "exposure",
                args.holdout_images,
                args.seed * 100000 + 90000,
                cohort="control_dev",
                exposure_profile=exposure_profile,
            )
        )
        write(
            root / "auxiliary-split-audit.json",
            controls.audit(auxiliary, raw, exposure_profile=exposure_profile),
        )
        raw.update(auxiliary)
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
    if auxiliary_images:
        auxiliary_sheet = Image.new("RGB", (96 * 8, 96 * 4))
        for i, image in enumerate(raw["exposure"]["pixels"][:32]):
            auxiliary_sheet.paste(Image.fromarray(image), (i % 8 * 96, i // 8 * 96))
        auxiliary_sheet.save(root / "actual-exposure-contact-sheet.png")
    train, dev = Prepared(raw["train"], device), Prepared(raw["dev"], device)
    train_tasks = np.asarray([r["task"] for r in raw["train"]["records"]])
    auxiliary_train = Prepared(raw["exposure"], device) if auxiliary_images else None
    auxiliary_dev = Prepared(raw["control_dev"], device) if auxiliary_images else None
    if auxiliary_train is not None:
        auxiliary_tasks = np.asarray([r["task"] for r in raw["exposure"]["records"]])
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
            indices = torch.tensor(
                rng.choice(pool, size=48 if auxiliary_train is not None else 64),
                device=device,
            )
            x, q, y = train.batch(indices)
            if auxiliary_train is not None:
                auxiliary_pool = (
                    np.flatnonzero(auxiliary_tasks != "pattern")
                    if schedule == "curriculum" and step <= args.steps // 3
                    else np.arange(len(auxiliary_train.labels))
                )
                ax, aq, ay = auxiliary_train.batch(
                    torch.tensor(rng.choice(auxiliary_pool, size=16), device=device)
                )
                x, q, y = torch.cat((x, ax)), torch.cat((q, aq)), torch.cat((y, ay))
            if model.reflection_consensus:
                x, q = views.augment_batch(x, q, rng)
            optimizer.param_groups[0]["lr"] = 0.001 * (
                0.2 + 0.8 * 0.5 * (1 + math.cos(math.pi * step / args.steps))
            )
            optimizer.zero_grad(set_to_none=True)
            logits = model(x, q)
            loss = masked_smoothing_loss(logits, y, args.label_smoothing)
            if consistency_amount:
                second_x, second_q = views.augment_batch(x, q, rng)
                loss = loss + consistency_amount * consistency_loss(
                    logits, model(second_x, second_q)
                )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0
            )
            optimizer.step()
            if step % args.eval_every == 0 or step == args.steps:
                # Checkpoint selection remains raw single-view dev CE, not
                # conservative scores with deliberately zeroed alternatives.
                p = probabilities(model, dev, single_view=True)
                score = balanced_loss(dev, p)
                native_score = score
                auxiliary_score = None
                if auxiliary_dev is not None:
                    auxiliary_score = balanced_loss(
                        auxiliary_dev,
                        probabilities(model, auxiliary_dev, single_view=True),
                    )
                    score = (native_score + auxiliary_score) / 2
                verify_inherited(model, inherited_state)
                point = {
                    "step": step,
                    "train_loss": float(loss.detach()),
                    "balanced_dev_ce": score,
                    "native_balanced_dev_ce": native_score,
                    "auxiliary_balanced_dev_ce": auxiliary_score,
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
                            "spatial_readout": model.spatial_readout_enabled,
                            "shape_edges": model.shape_edges_enabled,
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
    calibration_data = (
        join_data(raw["calibration"], raw["control_calibration"])
        if auxiliary_images
        else raw["calibration"]
    )
    calibration = Prepared(calibration_data, device)
    cohorts = ["native"] * len(raw["calibration"]["records"])
    if auxiliary_images:
        cohorts += ["authored"] * len(raw["control_calibration"]["records"])
    thresholds, policy = calibrate(
        calibration,
        probabilities(model, calibration),
        rule=calibration_rule,
        cohorts=cohorts,
    )
    write(root / "policy-frozen.json", policy)
    final_splits = ("final", "combinations", "transfer") + (
        ("control_final",) if auxiliary_images else ()
    )
    reports = {}
    for split in ("dev", *final_splits):
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
        single_p = (
            probabilities(model, group, single_view=True)
            if model.reflection_consensus
            else p
        )
        single_eval = evaluate(group, single_p, {task: 0 for task in course.VALUES})
        report["single_view_raw_argmax"] = {
            k: v for k, v in single_eval.items() if k != "predictions"
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
                    "single_view_probabilities": single_p.tolist(),
                    "single_view_raw_predictions": single_eval["predictions"],
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
        or (
            args.warm_candidate is not None
            and sha(args.warm_candidate) != candidate_anchor
        )
        or sha(winner["checkpoint"]) != winner["checkpoint_sha256"]
    ):
        raise ValueError("Source or frozen checkpoint changed")
    passed = blank["overall"]["accepted"] == 0 and all(
        all(
            task["false_assertions"] == 0
            and task["answerable_recall"] >= 0.8
            and task["unknown_recall"] >= 0.9
            for task in reports[split]["selected"]["tasks"].values()
        )
        for split in final_splits
    )
    passed = passed and all(
        reports[split]["selected"]["complete_visible_descriptions"][
            "all_three_correct_rate"
        ]
        >= 0.8
        and all(
            m["both_correct_rate"] is not None and m["both_correct_rate"] >= 0.8
            for m in reports[split]["selected"]["target_binding"].values()
        )
        for split in ("final", "combinations", "transfer")
    )
    result = {
        "schema": 1,
        "status": "BOUNDED_SYNTHETIC_SCREEN_PASSED"
        if passed
        else "NEEDS_WORK_NOT_PRODUCTION",
        "production_admitted": False,
        "numeric_backend": numeric_backend,
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
        "reflection_consensus": model.reflection_consensus,
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
    parser.add_argument(
        "--dataset-profile",
        choices=course.DATASET_PROFILES,
        default="legacy",
    )
    parser.add_argument("--warm-candidate", type=Path)
    parser.add_argument("--spatial-readout", action="store_true")
    parser.add_argument("--shape-edges", action="store_true")
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--reflection-consensus", action="store_true")
    parser.add_argument("--auxiliary-images", type=int, default=0)
    parser.add_argument(
        "--exposure-profile",
        choices=tuple(controls.EXPOSURE_PROFILES),
        default="standard",
    )
    parser.add_argument("--consistency-loss", type=float, default=0.0)
    parser.add_argument(
        "--calibration-rule", choices=CALIBRATION_RULES, default="maximum_coverage"
    )
    parser.add_argument(
        "--numeric-precision", choices=("legacy", "ieee"), default="legacy"
    )
    args = parser.parse_args()
    if min(args.steps, args.eval_every, args.train_images, args.holdout_images) < 1:
        parser.error("Positive experiment sizes required")
    run(args)

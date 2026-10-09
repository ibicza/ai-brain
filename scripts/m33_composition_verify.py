"""Independent arithmetic and inference replay, not independent semantic/blind review."""

import argparse
import gzip
import hashlib
import json
import math
import tarfile
from pathlib import Path

import numpy as np
import torch

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_objects as old


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def measure(gold, predicted):
    accepted = sum(p != c.UNKNOWN for p in predicted)
    positives = sum(g != c.UNKNOWN for g in gold)
    unknown = len(gold) - positives
    errors = sum(
        p != c.UNKNOWN and p != g for g, p in zip(gold, predicted, strict=True)
    )
    correct = sum(
        p == g and g != c.UNKNOWN for g, p in zip(gold, predicted, strict=True)
    )
    return {
        "examples": len(gold),
        "accepted": accepted,
        "false_assertions": errors,
        "accepted_error_rate": errors / accepted if accepted else None,
        "answerable_recall": correct / positives if positives else None,
        "unknown_recall": sum(
            g == p == c.UNKNOWN for g, p in zip(gold, predicted, strict=True)
        )
        / unknown
        if unknown
        else None,
    }


def equal(left, right):
    if left.keys() != right.keys():
        raise ValueError("Metric fields changed")
    for key, value in left.items():
        expected = right[key]
        if isinstance(value, float):
            if not math.isclose(value, expected, rel_tol=1e-7, abs_tol=1e-7):
                raise ValueError("Metric mismatch: " + key)
        elif value != expected:
            raise ValueError("Metric mismatch: " + key)


def decisions(p, records, thresholds):
    best = p.argmax(1)
    return [
        int(v)
        if thresholds[r["task"]] is not None and p[i, v] >= thresholds[r["task"]]
        else c.UNKNOWN
        for i, (v, r) in enumerate(zip(best, records, strict=True))
    ]


def replay(model, arrays, split, device, *, blank=False):
    pieces = []
    with torch.no_grad():
        for start in range(0, len(arrays[split + "_labels"]), 96):
            indices = arrays[split + "_image_index"][start : start + 96]
            pixels = (
                torch.from_numpy(arrays[split + "_pixels"][indices])
                .permute(0, 3, 1, 2)
                .float()
                .to(device)
                / 255
            )
            questions = torch.from_numpy(
                arrays[split + "_questions"][start : start + 96]
            ).to(device)
            if blank:
                pixels = torch.full_like(pixels, 0.5)
            pieces.append(model(pixels, questions).softmax(-1).cpu().numpy())
    return np.concatenate(pieces)


def verify(root, previous, capsule, output, device):
    if output.exists():
        raise ValueError("Fresh verification receipt required")
    protocol, freeze, result, policy = [
        read(root / name)
        for name in (
            "protocol.json",
            "candidate-freeze.json",
            "result.json",
            "policy-frozen.json",
        )
    ]
    if (
        sha(capsule) != protocol["source_capsule_sha256"]
        or sha(previous) != protocol["previous_sha256"]
        or sha(root / "dataset.npz") != freeze["dataset_sha256"]
        or sha(root / "dataset-records.json.gz") != freeze["records_sha256"]
        or sha(root / "protocol.json") != freeze["protocol_sha256"]
        or result["production_admitted"]
    ):
        raise ValueError("Frozen inputs/status changed")
    sources = read(root.parent / "source-manifest.json")
    with tarfile.open(capsule) as archive:
        sealed_sources = json.load(archive.extractfile("source-manifest.json"))
    if sources != sealed_sources:
        raise ValueError("Source manifest differs from sealed capsule")
    if (
        protocol.get("candidate_anchor_sha256") is not None
        and sha(root.parent / "warm-candidate.pt")
        != protocol["candidate_anchor_sha256"]
    ):
        raise ValueError("Warm candidate anchor changed")
    for row in sources["files"]:
        if sha(root.parent / row["file"]) != row["sha256"]:
            raise ValueError("Frozen source capsule file changed")
    if freeze["winner"] != min(freeze["trials"], key=lambda r: r["best_dev_ce"]):
        raise ValueError("Winner not selected by development")
    for trial in freeze["trials"]:
        if (
            trial["best_dev_ce"] != min(r["balanced_dev_ce"] for r in trial["history"])
            or sha(root / trial["schedule"] / "best.pt") != trial["checkpoint_sha256"]
        ):
            raise ValueError("Trial lineage mismatch")
    checkpoint_path = root / freeze["winner"]["schedule"] / "best.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if (
        checkpoint["previous_sha256"] != sha(previous)
        or tuple(checkpoint["answers"]) != c.ANSWERS
        or checkpoint["new_words"] != c.NEW_WORDS
    ):
        raise ValueError("Vocabulary or inherited weight mismatch")
    if (
        result["checkpoint_sha256"] != sha(checkpoint_path)
        or result["inherited_checkpoint_sha256"] != sha(previous)
        or result["winner"] != freeze["winner"]["schedule"]
        or result["capacity"] != protocol["capacity"]
    ):
        raise ValueError("Result lineage metadata differs from freeze")
    prior = torch.load(previous, map_location="cpu", weights_only=True)
    torch.set_num_threads(2)
    model_options = {"attribute_attention": checkpoint["attribute_attention"]}
    # Replay pre-spatial capsules without rewriting their frozen source module.
    if checkpoint.get("spatial_readout", False):
        model_options["spatial_readout"] = True
    if checkpoint.get("shape_edges", False):
        model_options["shape_edges"] = True
    model = (
        c.CompositionModel(
            old.ObjectsModel.from_checkpoint(prior),
            **model_options,
        )
        .to(device)
        .eval()
    )
    model.load_candidate(checkpoint["candidate"])
    if any(
        not torch.equal(model.inherited.state_dict()[k].cpu(), v)
        for k, v in prior["model"].items()
    ):
        raise ValueError("Inherited tensors changed")
    # NpzFile decompresses on EVERY __getitem__. Question correspondence and
    # replay loops must use an eagerly loaded immutable snapshot, not repeatedly
    # expand multi-megabyte arrays for each of tens of thousands of questions.
    with np.load(root / "dataset.npz", allow_pickle=False) as stored_arrays:
        arrays = {key: stored_arrays[key] for key in stored_arrays.files}
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as f:
        source_records = json.load(f)
    for split in source_records:
        records = source_records[split]["records"]
        if [r["answer"] for r in records] != arrays[split + "_labels"].tolist():
            raise ValueError("Labels differ from sealed records")
        for index, pixel in enumerate(arrays[split + "_pixels"]):
            digest = hashlib.sha256(pixel.tobytes()).hexdigest()
            if any(
                r["image_sha256"] != digest for r in records[index * 6 : index * 6 + 6]
            ):
                raise ValueError("Exact pixel input hash differs")
        for index, record in enumerate(records):
            if (
                c.encode_question(record["question"])
                != arrays[split + "_questions"][index].tolist()
                or c.QUERIES[record["question"]] != (record["task"], record["side"])
                or int(arrays[split + "_image_index"][index]) != index // 6
            ):
                raise ValueError("Question target/input correspondence differs")
            stored_scene = source_records[split]["scenes"][index // 6]
            scene = c.Scene(
                stored_scene["identity"],
                stored_scene["seed"],
                tuple(c.Item(**item) for item in stored_scene["items"]),
                stored_scene["style"],
            )
            if (
                record["scene_id"] != scene.identity
                or scene.gold(record["task"], record["side"]) != record["answer"]
            ):
                raise ValueError("Oracle scene and target label differ")
    calibration = replay(model, arrays, "calibration", device)
    thresholds = {task: entry["threshold"] for task, entry in policy["tasks"].items()}
    if thresholds != result["thresholds"]:
        raise ValueError("Result thresholds differ from frozen calibration")
    records = source_records["calibration"]["records"]
    predicted = decisions(calibration, records, thresholds)
    for task in c.VALUES:
        indices = [i for i, r in enumerate(records) if r["task"] == task]
        actual = measure(
            [records[i]["answer"] for i in indices], [predicted[i] for i in indices]
        )
        equal(actual, policy["tasks"][task]["metrics"])
        if thresholds[task] is not None and (
            actual["false_assertions"]
            or actual["accepted"] < policy["minimum_accepted_per_task"]
        ):
            raise ValueError("Invalid calibration selection")
        eligible = []
        task_records = [records[i] for i in indices]
        task_gold = [r["answer"] for r in task_records]
        for threshold in (0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 0.9999):
            candidate = decisions(calibration[indices], task_records, {task: threshold})
            metrics = measure(task_gold, candidate)
            if (
                metrics["false_assertions"] == 0
                and metrics["accepted"] >= policy["minimum_accepted_per_task"]
            ):
                eligible.append((metrics["accepted"], threshold))
        best = max(eligible) if eligible else None
        if thresholds[task] != (best[1] if best else None):
            raise ValueError("Calibration threshold not selected by frozen rule")
    checks = {}
    for split in ("dev", "final", "combinations", "transfer"):
        with gzip.open(
            root / (split + "-predictions.json.gz"), "rt", encoding="utf-8"
        ) as f:
            saved = json.load(f)
        records = source_records[split]["records"]
        if records != saved["records"]:
            raise ValueError("Evaluation source rows changed")
        p = np.asarray(saved["probabilities"])
        actual_p = replay(model, arrays, split, device)
        if not np.allclose(actual_p, p, atol=2e-6, rtol=2e-5):
            raise ValueError("Model inference replay differs")
        predicted = decisions(p, records, thresholds)
        if (
            decisions(actual_p, records, thresholds) != predicted
            or actual_p.argmax(1).tolist() != saved["raw_predictions"]
        ):
            raise ValueError("Replayed decisions differ despite close probabilities")
        if (
            predicted != saved["selected"]
            or p.argmax(1).tolist() != saved["raw_predictions"]
        ):
            raise ValueError("Saved answer decisions differ")
        gold = [r["answer"] for r in records]
        report = result["reports"][split]
        equal(measure(gold, predicted), report["selected"]["overall"])
        equal(measure(gold, saved["raw_predictions"]), report["raw_argmax"]["overall"])
        for task in c.VALUES:
            indices = [i for i, r in enumerate(records) if r["task"] == task]
            equal(
                measure([gold[i] for i in indices], [predicted[i] for i in indices]),
                report["selected"]["tasks"][task],
            )
            equal(
                measure(
                    [gold[i] for i in indices],
                    [saved["raw_predictions"][i] for i in indices],
                ),
                report["raw_argmax"]["tasks"][task],
            )
            offset = list(c.VALUES).index(task)
            pairs = [
                (i + offset, i + 3 + offset)
                for i in range(0, len(gold), 6)
                if gold[i + offset] != gold[i + 3 + offset]
                and c.UNKNOWN not in (gold[i + offset], gold[i + 3 + offset])
            ]
            equal(
                {
                    "eligible_scene_pairs": len(pairs),
                    "both_correct_rate": sum(
                        predicted[a] == gold[a] and predicted[b] == gold[b]
                        for a, b in pairs
                    )
                    / len(pairs)
                    if pairs
                    else None,
                },
                report["selected"]["target_binding"][task],
            )
        visible = [
            predicted[i : i + 3] == gold[i : i + 3]
            for i in range(0, len(gold), 3)
            if all(g != c.UNKNOWN for g in gold[i : i + 3])
        ]
        equal(
            {
                "eligible_objects": len(visible),
                "all_three_correct_rate": sum(visible) / len(visible),
            },
            report["selected"]["complete_visible_descriptions"],
        )
        checks[split] = {
            "inference_replayed": True,
            "arithmetic_verified": True,
            **measure(gold, predicted),
        }
    blank_p = replay(model, arrays, "final", device, blank=True)
    final_records = source_records["final"]["records"]
    blank_predictions = decisions(blank_p, final_records, thresholds)
    blank_gold = [r["answer"] for r in final_records]
    blank_metrics = measure(blank_gold, blank_predictions)
    equal(blank_metrics, read(root / "blank-image-ablation.json")["overall"])
    gate = all(
        all(
            m["false_assertions"] == 0
            and m["answerable_recall"] >= 0.8
            and m["unknown_recall"] >= 0.9
            for m in result["reports"][split]["selected"]["tasks"].values()
        )
        for split in ("final", "combinations", "transfer")
    )
    if "acceptance" in protocol:
        if protocol["acceptance"] != {
            "task_positive_recall_min": 0.8,
            "task_unknown_recall_min": 0.9,
            "accepted_errors_max": 0,
            "complete_description_recall_min": 0.8,
            "both_targets_correct_min": 0.8,
            "blank_image_accepted_max": 0,
        }:
            raise ValueError("Acceptance protocol weakened or changed")
        gate = (
            gate
            and blank_metrics["accepted"] == 0
            and all(
                result["reports"][split]["selected"]["complete_visible_descriptions"][
                    "all_three_correct_rate"
                ]
                >= 0.8
                and all(
                    m["both_correct_rate"] is not None and m["both_correct_rate"] >= 0.8
                    for m in result["reports"][split]["selected"][
                        "target_binding"
                    ].values()
                )
                for split in ("final", "combinations", "transfer")
            )
        )
    if gate != (result["status"] == "BOUNDED_SYNTHETIC_SCREEN_PASSED"):
        raise ValueError("Reported gate contradicts measurements")
    receipt = {
        "schema": 1,
        "status": "INFERENCE_AND_ARITHMETIC_VERIFIED",
        "model_status": result["status"],
        "capsule_sha256": sha(capsule),
        "checkpoint_sha256": sha(checkpoint_path),
        "dataset_sha256": sha(root / "dataset.npz"),
        "checks": checks,
        "inherited_tensors_byte_preserved": True,
        "blank_input_accepted": blank_metrics["accepted"],
        "blank_inference_replayed": True,
        "question_and_oracle_correspondence_verified": True,
        "production_admitted": False,
        "limits": "Separate arithmetic implementation and inference replay, not independent semantic annotation or external-source blind examination.",
    }
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": receipt["status"], "model_status": receipt["model_status"]}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "previous", "capsule", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    verify(
        args.root.resolve(),
        args.previous.resolve(),
        args.capsule.resolve(),
        args.output.resolve(),
        args.device,
    )

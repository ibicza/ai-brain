"""Independent arithmetic and inference replay, not independent semantic/blind review."""

import argparse
import gzip
import hashlib
import json
import math
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


def replay(model, arrays, split, device):
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
    prior = torch.load(previous, map_location="cpu", weights_only=True)
    torch.set_num_threads(2)
    model = (
        c.CompositionModel(
            old.ObjectsModel.from_checkpoint(prior),
            attribute_attention=checkpoint["attribute_attention"],
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
    arrays = np.load(root / "dataset.npz", allow_pickle=False)
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
    calibration = replay(model, arrays, "calibration", device)
    thresholds = {task: entry["threshold"] for task, entry in policy["tasks"].items()}
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
    gate = all(
        all(
            m["false_assertions"] == 0
            and m["answerable_recall"] >= 0.8
            and m["unknown_recall"] >= 0.9
            for m in result["reports"][split]["selected"]["tasks"].values()
        )
        for split in ("final", "combinations", "transfer")
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
        "blank_input_accepted": read(root / "blank-image-ablation.json")["overall"][
            "accepted"
        ],
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

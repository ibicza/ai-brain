"""Frozen-source development-only model-agreement study; no training or final."""

import argparse
import gzip
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fuse(scores, unknown):
    """Unanimous argmax, minimum score; disagreement is explicitly UNKNOWN."""
    import numpy as np

    p = np.asarray(scores)
    if (
        p.ndim != 3
        or p.shape[0] < 2
        or type(unknown) is not int
        or not 0 <= unknown < p.shape[-1]
        or not np.isfinite(p).all()
        or np.any((p < 0) | (p > 1))
        or not np.allclose(p.sum(-1), 1, atol=1e-5)
    ):
        raise ValueError("Invalid model agreement scores")
    best = p.argmax(-1)
    agreed = (best == best[0]).all(0) & (best[0] != unknown)
    minimum = p.max(-1).min(0)
    result = np.zeros_like(p[0])
    result[:, unknown] = 1
    rows = np.flatnonzero(agreed)
    result[rows, best[0, agreed]] = minimum[agreed]
    result[rows, unknown] = 1 - minimum[agreed]
    return result


def run(reference, output, device):
    if output.exists():
        raise ValueError("Fresh development study required")
    root = reference / "experiment"
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    freeze = json.loads((root / "candidate-freeze.json").read_text(encoding="utf-8"))
    paths = [
        reference / "source-capsule.tgz",
        reference / "previous.pt",
        root / "dataset.npz",
        root / "dataset-records.json.gz",
        root / "candidate-freeze.json",
        root / "protocol.json",
        root / "policy-frozen.json",
    ]
    paths += [root / name / "best.pt" for name in ("joint", "curriculum")]
    hashes = {str(p): sha(p) for p in paths}
    if (
        hashes[str(reference / "source-capsule.tgz")]
        != protocol["source_capsule_sha256"]
        or hashes[str(reference / "previous.pt")] != protocol["previous_sha256"]
        or hashes[str(root / "protocol.json")] != freeze["protocol_sha256"]
        or hashes[str(root / "dataset.npz")] != freeze["dataset_sha256"]
        or hashes[str(root / "dataset-records.json.gz")] != freeze["records_sha256"]
    ):
        raise ValueError("Frozen reference changed")
    output.mkdir(parents=True)
    executed_source = output / "diagnostic-executed.py"
    shutil.copy2(__file__, executed_source)
    executed_hash = sha(executed_source)
    extracted = output / "frozen-source"
    with tarfile.open(reference / "source-capsule.tgz") as archive:
        archive.extractall(extracted, filter="data")
    manifest = json.loads((extracted / "source-manifest.json").read_text())
    for row in manifest["files"]:
        if sha(extracted / row["file"]) != row["sha256"]:
            raise ValueError("Frozen code differs from original capsule")
    # Insert before importing any project/script code. Editable installation and
    # the current checkout must not silently replace original inference code.
    sys.path.insert(0, str(extracted / "scripts"))
    sys.path.insert(0, str(extracted / "src"))
    import numpy as np
    import torch
    from m33_primary_composition_pilot import (
        Prepared,
        balanced_loss,
        evaluate,
        probabilities,
        write,
    )

    from ai_brain.training import primary_composition as c
    from ai_brain.training import primary_objects as old

    if (
        Path(c.__file__).resolve()
        != (extracted / "src/ai_brain/training/primary_composition.py").resolve()
    ):
        raise ValueError("Inference module escaped frozen source")
    torch.set_num_threads(2)
    splits = ("dev", "control_dev") if protocol.get("auxiliary_images", 0) else ("dev",)
    with np.load(root / "dataset.npz", allow_pickle=False) as store:
        arrays = {
            split: {
                key: store[split + "_" + key]
                for key in ("pixels", "questions", "labels", "image_index")
            }
            for split in splits
        }
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as stream:
        records = json.load(stream)
    policy = json.loads((root / "policy-frozen.json").read_text(encoding="utf-8"))
    thresholds = {task: entry["threshold"] for task, entry in policy["tasks"].items()}
    prepared = {}
    for split in splits:
        arrays[split].update(records[split])
        prepared[split] = Prepared(arrays[split], device)
    prior = torch.load(reference / "previous.pt", map_location="cpu", weights_only=True)
    groups, model_scores, summary = {}, {}, {}
    for schedule in ("joint", "curriculum"):
        path = root / schedule / "best.pt"
        trial = next(t for t in freeze["trials"] if t["schedule"] == schedule)
        if sha(path) != trial["checkpoint_sha256"]:
            raise ValueError("Development candidate differs from freeze")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = (
            c.CompositionModel(
                old.ObjectsModel.from_checkpoint(prior),
                spatial_readout=checkpoint.get("spatial_readout", False),
                shape_edges=checkpoint.get("shape_edges", False),
                attribute_attention=checkpoint["attribute_attention"],
            )
            .to(device)
            .eval()
        )
        model.load_candidate(checkpoint["candidate"])
        model.reflection_consensus = protocol.get("reflection_consensus", False)
        model_scores[schedule], groups[schedule] = {}, {}
        for split, data in prepared.items():
            p = probabilities(model, data)
            raw = probabilities(model, data, single_view=True)
            model_scores[schedule][split] = p
            metrics = evaluate(data, p, thresholds)
            groups[schedule][split] = {
                k: v for k, v in metrics.items() if k != "predictions"
            }
            groups[schedule][split]["raw_balanced_ce"] = balanced_loss(data, raw)
            with gzip.open(
                output / (schedule + "-" + split + "-scores.json.gz"),
                "wt",
                encoding="utf-8",
            ) as stream:
                json.dump(
                    {
                        "probabilities": p.tolist(),
                        "single_view_probabilities": raw.tolist(),
                        "selected": metrics["predictions"],
                    },
                    stream,
                )
        summary[schedule] = float(
            np.mean([v["raw_balanced_ce"] for v in groups[schedule].values()])
        )
        if not np.isclose(summary[schedule], trial["best_dev_ce"], atol=2e-6):
            write(
                output / "failure.json",
                {
                    "status": "DEVELOPMENT_REPLAY_OUTSIDE_STRICT_TOLERANCE",
                    "device": str(device),
                    "schedule": schedule,
                    "actual_dev_ce": summary[schedule],
                    "frozen_dev_ce": trial["best_dev_ce"],
                    "absolute_tolerance": 2e-6,
                    "reference_hashes": hashes,
                    "executed_script_sha256": executed_hash,
                    "production_admitted": False,
                },
            )
            raise ValueError(
                f"Original development score not reproduced: {summary[schedule]} versus {trial['best_dev_ce']}"
            )
    groups["two_candidate_agreement"] = {}
    for split, data in prepared.items():
        p = fuse([model_scores[s][split] for s in ("joint", "curriculum")], c.UNKNOWN)
        metrics = evaluate(data, p, thresholds)
        groups["two_candidate_agreement"][split] = {
            k: v for k, v in metrics.items() if k != "predictions"
        }
        write(
            output / ("agreement-" + split + "-predictions.json"),
            metrics["predictions"],
        )
    if any(sha(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("Reference changed during development study")
    if sha(Path(__file__)) != executed_hash:
        raise ValueError("Diagnostic script changed during execution")
    report = {
        "schema": 1,
        "status": "KNOWN_DEVELOPMENT_AGREEMENT_STUDY_REPLAYED",
        "reference_hashes": hashes,
        "splits": list(splits),
        "frozen_thresholds": thresholds,
        "groups": groups,
        "balanced_dev_ce": summary,
        "device": str(device),
        "executed_script_sha256": executed_hash,
        "training_or_calibration": False,
        "production_admitted": False,
        "limits": "Known development data only, original frozen inference code. Two models share the same inherited tensors; not a full independent deep ensemble, not a blind final, not a calibrated uncertainty guarantee.",
    }
    write(output / "result.json", report)
    print(
        json.dumps({"status": report["status"], "balanced_dev_ce": summary}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    run(args.reference.resolve(), args.output.resolve(), args.device)

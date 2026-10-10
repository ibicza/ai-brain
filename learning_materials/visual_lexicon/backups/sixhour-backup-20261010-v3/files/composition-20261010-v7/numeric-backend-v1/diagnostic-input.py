"""Known-dev CPU/CUDA precision intervention; no training or final access."""

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


def compare(reference, candidate):
    import numpy as np

    a, b = np.asarray(reference), np.asarray(candidate)
    if (
        a.shape != b.shape
        or a.ndim != 2
        or not a.size
        or not (np.isfinite(a).all() and np.isfinite(b).all())
    ):
        raise ValueError("Comparable finite score matrices required")
    return {
        "examples": len(a),
        "max_absolute_score_difference": float(np.abs(a - b).max()),
        "mean_absolute_score_difference": float(np.abs(a - b).mean()),
        "raw_argmax_disagreements": int((a.argmax(-1) != b.argmax(-1)).sum()),
    }


def run(reference, output, device):
    if output.exists() or device != "cuda":
        raise ValueError("Fresh CUDA precision study required")
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
        root / "joint/best.pt",
    ]
    hashes = {str(p): sha(p) for p in paths}
    if (
        sha(reference / "source-capsule.tgz") != protocol["source_capsule_sha256"]
        or sha(reference / "previous.pt") != protocol["previous_sha256"]
        or sha(root / "protocol.json") != freeze["protocol_sha256"]
        or sha(root / "dataset.npz") != freeze["dataset_sha256"]
        or sha(root / "dataset-records.json.gz") != freeze["records_sha256"]
    ):
        raise ValueError("Frozen reference changed")
    trial = next(t for t in freeze["trials"] if t["schedule"] == "joint")
    if sha(root / "joint/best.pt") != trial["checkpoint_sha256"]:
        raise ValueError("Frozen joint checkpoint changed")
    output.mkdir(parents=True)
    executed = output / "diagnostic-executed.py"
    shutil.copy2(__file__, executed)
    executed_hash = sha(executed)
    extracted = output / "frozen-source"
    with tarfile.open(reference / "source-capsule.tgz") as archive:
        archive.extractall(extracted, filter="data")
    manifest = json.loads((extracted / "source-manifest.json").read_text())
    if any(sha(extracted / r["file"]) != r["sha256"] for r in manifest["files"]):
        raise ValueError("Frozen source differs")
    sys.path.insert(0, str(extracted / "scripts"))
    sys.path.insert(0, str(extracted / "src"))
    import numpy as np
    import torch
    from m33_primary_composition_pilot import Prepared, balanced_loss, probabilities

    from ai_brain.training import primary_composition as c
    from ai_brain.training import primary_objects as old

    if (
        Path(c.__file__).resolve()
        != (extracted / "src/ai_brain/training/primary_composition.py").resolve()
    ):
        raise ValueError("Inference module escaped frozen source")
    if not torch.cuda.is_available():
        raise ValueError("CUDA precision intervention unavailable")
    torch.set_num_threads(2)
    splits = ("dev", "control_dev") if protocol.get("auxiliary_images", 0) else ("dev",)
    with np.load(root / "dataset.npz", allow_pickle=False) as store:
        arrays = {
            s: {
                k: store[s + "_" + k]
                for k in ("pixels", "questions", "labels", "image_index")
            }
            for s in splits
        }
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as stream:
        records = json.load(stream)
    for split in splits:
        arrays[split].update(records[split])
    prior = torch.load(reference / "previous.pt", map_location="cpu", weights_only=True)
    checkpoint = torch.load(
        root / "joint/best.pt", map_location="cpu", weights_only=True
    )
    model = c.CompositionModel(
        old.ObjectsModel.from_checkpoint(prior),
        spatial_readout=checkpoint.get("spatial_readout", False),
        shape_edges=checkpoint.get("shape_edges", False),
        attribute_attention=checkpoint["attribute_attention"],
    ).eval()
    model.load_candidate(checkpoint["candidate"])
    initial_backend = {
        "global": torch.backends.fp32_precision,
        "cuda_matmul": torch.backends.cuda.matmul.fp32_precision,
        "cudnn_conv": torch.backends.cudnn.conv.fp32_precision,
    }
    # PyTorch 2.9 API only: do not mix setters for legacy allow_tf32 flags.
    variants = (
        ("cpu_ieee", "cpu", "ieee"),
        ("cuda_tf32_conv", "cuda", "tf32"),
        ("cuda_ieee_conv", "cuda", "ieee"),
    )
    all_scores, losses = {}, {}
    for name, backend, precision in variants:
        torch.backends.fp32_precision = "ieee"
        torch.backends.cuda.matmul.fp32_precision = "ieee"
        torch.backends.cudnn.conv.fp32_precision = precision
        model = model.to(backend)
        all_scores[name], split_losses = {}, {}
        for split in splits:
            prepared = Prepared(arrays[split], backend)
            scores = probabilities(model, prepared, single_view=True)
            all_scores[name][split] = scores
            split_losses[split] = balanced_loss(prepared, scores)
            with gzip.open(
                output / (name + "-" + split + "-scores.json.gz"),
                "wt",
                encoding="utf-8",
            ) as stream:
                json.dump({"single_view_probabilities": scores.tolist()}, stream)
        losses[name] = {
            "split_balanced_ce": split_losses,
            "balanced_ce": float(np.mean(list(split_losses.values()))),
        }
        print(json.dumps({"variant": name, **losses[name]}), flush=True)
    comparisons = {
        name: {
            split: compare(all_scores["cpu_ieee"][split], all_scores[name][split])
            for split in splits
        }
        for name in ("cuda_tf32_conv", "cuda_ieee_conv")
    }
    if (
        any(sha(Path(p)) != h for p, h in hashes.items())
        or sha(Path(__file__)) != executed_hash
    ):
        raise ValueError("Diagnostic inputs or source changed")
    report = {
        "schema": 1,
        "status": "KNOWN_DEV_NUMERIC_INTERVENTION_COMPLETE",
        "reference_hashes": hashes,
        "executed_script_sha256": executed_hash,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "gpu": torch.cuda.get_device_name(),
        "initial_backend": initial_backend,
        "splits": list(splits),
        "losses": losses,
        "comparisons_to_cpu": comparisons,
        "original_joint_dev_ce": trial["best_dev_ce"],
        "training_or_calibration": False,
        "production_admitted": False,
        "limits": "Known dev only, fixed original source/checkpoint/data and batch size. Numeric intervention, not a final model exam. Precision tolerance is not relaxed and old failed study is not retroactively accepted. Similarity is not universal CPU/GPU bit equality.",
    }
    (output / "result.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "losses": losses}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    run(args.reference.resolve(), args.output.resolve(), args.device)

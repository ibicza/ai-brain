"""Fixed-policy cold-family screen with original capsule inference, no fitting."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import sys
import tarfile
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(reference, output, count, seed, device):
    if output.exists():
        raise ValueError("Fresh cold screen required")
    if (
        type(count) is not int
        or not 12 <= count <= 6000
        or type(seed) is not int
        or seed < 0
    ):
        raise ValueError("Fresh bounded cold corpus required")
    if any(name == "ai_brain" or name.startswith("ai_brain.") for name in sys.modules):
        raise ValueError(
            "Cold screen requires fresh interpreter for original inference"
        )
    root = reference / "experiment"
    protocol, freeze, result, policy = (
        read(root / name)
        for name in (
            "protocol.json",
            "candidate-freeze.json",
            "result.json",
            "policy-frozen.json",
        )
    )
    schedule = freeze["winner"]["schedule"]
    if schedule not in ("joint", "curriculum"):
        raise ValueError("Registered frozen candidate required")
    checkpoint_path = root / schedule / "best.pt"
    capsule = reference / "source-capsule.tgz"
    paths = [
        capsule,
        reference / "previous.pt",
        checkpoint_path,
        root / "protocol.json",
        root / "candidate-freeze.json",
        root / "policy-frozen.json",
        root / "result.json",
        root / "dataset-records.json.gz",
    ]
    hashes = {str(path): sha(path) for path in paths}
    if (
        sha(capsule) != protocol["source_capsule_sha256"]
        or sha(reference / "previous.pt") != protocol["previous_sha256"]
        or sha(checkpoint_path) != freeze["winner"]["checkpoint_sha256"]
        or sha(checkpoint_path) != result["checkpoint_sha256"]
        or sha(root / "protocol.json") != freeze["protocol_sha256"]
        or sha(root / "dataset-records.json.gz") != freeze["records_sha256"]
    ):
        raise ValueError("Original frozen source/weights/records changed")
    thresholds = {task: row["threshold"] for task, row in policy["tasks"].items()}
    if thresholds != result["thresholds"]:
        raise ValueError("Reference frozen thresholds changed")
    output.mkdir(parents=True)
    script_path = Path(__file__).resolve()
    generator_path = script_path.with_name("m33_composition_novel_controls.py")
    source_hashes = {str(path): sha(path) for path in (script_path, generator_path)}
    for path in (script_path, generator_path):
        shutil.copy2(path, output / path.name)
    extracted = output / "frozen-source"
    with tarfile.open(capsule) as archive:
        archive.extractall(extracted, filter="data")
    manifest = read(extracted / "source-manifest.json")
    for entry in manifest["files"]:
        path = (extracted / entry["file"]).resolve()
        if not path.is_relative_to(extracted.resolve()) or sha(path) != entry["sha256"]:
            raise ValueError("Original inference source bytes differ")
    sys.path.insert(0, str(extracted / "scripts"))
    sys.path.insert(0, str(extracted / "src"))
    import m33_composition_verify as verifier
    import m33_primary_composition_pilot as pilot
    import numpy as np
    import torch
    from m33_composition_verify import decisions, equal, measure, replay
    from m33_primary_composition_pilot import Prepared, evaluate, probabilities, write
    from PIL import Image

    from ai_brain.training import primary_composition as c
    from ai_brain.training import primary_numeric_backend as numeric
    from ai_brain.training import primary_objects as old

    for module, relative in (
        (c, "src/ai_brain/training/primary_composition.py"),
        (verifier, "scripts/m33_composition_verify.py"),
        (pilot, "scripts/m33_primary_composition_pilot.py"),
        (numeric, "src/ai_brain/training/primary_numeric_backend.py"),
        (old, "src/ai_brain/training/primary_objects.py"),
    ):
        if Path(module.__file__).resolve() != (extracted / relative).resolve():
            raise ValueError("Inference escaped original source capsule")
    torch.set_num_threads(2)
    backend = numeric.check_contract(protocol["numeric_backend"])
    spec = importlib.util.spec_from_file_location("cold_generator", generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    prior = torch.load(reference / "previous.pt", map_location="cpu", weights_only=True)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if (
        checkpoint["previous_sha256"] != sha(reference / "previous.pt")
        or tuple(checkpoint["answers"]) != c.ANSWERS
    ):
        raise ValueError("Cold inference vocabulary/inheritance differs")
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
    acceptance = {
        "accepted_errors_max": 0,
        "positive_recall_min": 0.8,
        "unknown_recall_min": 0.9,
        "per_family_and_task": True,
        "blank_accepted_max": 0,
    }
    write(
        output / "preregistered-freeze.json",
        {
            "reference_hashes": hashes,
            "screen_source_hashes": source_hashes,
            "count": count,
            "seed": seed,
            "families": generator.FAMILIES,
            "thresholds": thresholds,
            "numeric_backend": backend,
            "acceptance": acceptance,
            "training_or_calibration": False,
            "production_admitted": False,
            "limits": "Cold authored unsupported contours, shared Pillow; no photos or independent semantic examiner. UNKNOWN means unsupported by the four-shape readout.",
        },
    )
    data = generator.generate(count, seed, c)
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as stream:
        original = json.load(stream)
    old_seeds = {s["seed"] for group in original.values() for s in group["scenes"]}
    old_shapes = {
        item["shape"]
        for group in original.values()
        for scene in group["scenes"]
        for item in scene["items"]
    }
    if old_seeds & {s["seed"] for s in data["scenes"]} or old_shapes & set(
        generator.FAMILIES
    ):
        raise ValueError("Cold seeds/families present in original course")
    arrays = {
        "cold_" + name: data[name]
        for name in ("pixels", "questions", "labels", "image_index")
    }
    np.savez_compressed(output / "dataset.npz", **arrays)
    with gzip.open(output / "records.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(
            {name: data[name] for name in ("records", "scenes")},
            stream,
            ensure_ascii=False,
        )
    sheet = Image.new("RGB", (768, 384))
    for i, pixels in enumerate(data["pixels"][:32]):
        sheet.paste(Image.fromarray(pixels), (i % 8 * 96, i // 8 * 96))
    sheet.save(output / "actual-cold-inputs.png")
    prepared = Prepared(data, device)
    scores = probabilities(model, prepared)
    evaluated = evaluate(prepared, scores, thresholds)
    single = probabilities(model, prepared, single_view=True)
    raw = evaluate(prepared, single, {task: 0 for task in c.VALUES})
    repeated = replay(
        model, arrays, "cold", device, reflection_consensus=model.reflection_consensus
    )
    selected = decisions(repeated, data["records"], thresholds)
    if (
        not np.allclose(scores, repeated, atol=2e-6, rtol=2e-5)
        or selected != evaluated["predictions"]
    ):
        raise ValueError("Cold inference replay differs")
    equal(measure(data["labels"].tolist(), selected), evaluated["overall"])
    groups = {}
    for family in (*generator.FAMILIES, *c.SHAPES):
        groups[family] = {}
        for task in c.VALUES:
            indices = [
                i
                for i, row in enumerate(data["records"])
                if row["family"] == family and row["task"] == task
            ]
            groups[family][task] = measure(
                [int(data["labels"][i]) for i in indices],
                [selected[i] for i in indices],
            )
    for task in c.VALUES:
        indices = [i for i, row in enumerate(data["records"]) if row["task"] == task]
        equal(
            measure(
                [int(data["labels"][i]) for i in indices],
                [selected[i] for i in indices],
            ),
            evaluated["tasks"][task],
        )
    blank = replay(
        model,
        arrays,
        "cold",
        device,
        blank=True,
        reflection_consensus=model.reflection_consensus,
    )
    blank_selected = decisions(blank, data["records"], thresholds)
    blank_accepted = sum(answer != c.UNKNOWN for answer in blank_selected)
    passed = blank_accepted == 0 and all(
        row["examples"] > 0
        and row["false_assertions"] == 0
        and (row["answerable_recall"] is None or row["answerable_recall"] >= 0.8)
        and (row["unknown_recall"] is None or row["unknown_recall"] >= 0.9)
        for group in groups.values()
        for row in group.values()
    )
    if any(
        sha(Path(path)) != digest
        for path, digest in {**hashes, **source_hashes}.items()
    ):
        raise ValueError("Original reference/screen source changed")
    with gzip.open(output / "predictions.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(
            {
                "probabilities": scores.tolist(),
                "selected": selected,
                "single_view_probabilities": single.tolist(),
                "single_view_raw_predictions": raw["predictions"],
            },
            stream,
        )
    report = {
        "status": "COLD_FAMILY_SCREEN_PASSED"
        if passed
        else "COLD_FAMILY_FAILURE_NOT_PRODUCTION",
        "selected": {
            key: value for key, value in evaluated.items() if key != "predictions"
        },
        "single_view_raw_argmax": {
            key: value for key, value in raw.items() if key != "predictions"
        },
        "per_family": groups,
        "blank_accepted": blank_accepted,
        "independent_inference_and_arithmetic_replayed": True,
        "dataset_sha256": sha(output / "dataset.npz"),
        "records_sha256": sha(output / "records.json.gz"),
        "preregistered_freeze_sha256": sha(output / "preregistered-freeze.json"),
        "original_inference_capsule_sha256": sha(capsule),
        "production_admitted": False,
    }
    write(output / "result.json", report)
    write(
        output / "artifact-manifest.json",
        {
            "files": [
                {"file": path.name, "sha256": sha(path)}
                for path in sorted(output.iterdir())
                if path.is_file()
            ]
        },
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "overall": report["selected"]["overall"],
                "blank_accepted": blank_accepted,
            }
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    run(
        args.reference.resolve(),
        args.output.resolve(),
        args.count,
        args.seed,
        args.device,
    )

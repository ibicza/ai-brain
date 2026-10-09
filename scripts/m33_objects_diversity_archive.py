"""Seal diversity evidence without changing prior results or accepted weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_expansion_archive import ANCHOR, POLICY, bundle
from m33_verify_objects_evidence import verify

PARENT = "5b03f850d15937f45acd413b5e355858e6b2c7fe"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def result(root, repo):
    test_log = root / "focused-regression.log"
    if "270 passed, 2 skipped" not in test_log.read_text(encoding="utf-8-sig"):
        raise ValueError("Expected focused regression evidence missing")
    data = root / "prepared-v1"
    experiment = root / "development-v1/final-evaluation"
    report = load(experiment / "report.json")
    selection = load(root / "development-v1/selection-frozen.json")
    dataset = load(data / "dataset.json")
    diagnostic = load(experiment / "calibration-diagnostics.json")
    transfer = load(root / "v1-post-diagnostic-transfer-receipt.json")
    audit = verify(experiment, data)
    if (
        sha(experiment / "best.pt") != selection["winner"]["checkpoint_sha256"]
        or sha(root / "development-v1/selection-frozen.json")
        != report["selection_receipt_sha256"]
        or diagnostic["script_sha256"]
        != sha(repo / "scripts/m33_objects_calibration_diagnostics.py")
        or not transfer["accepted_checkpoint_unchanged"]
        or not transfer["accepted_policy_unchanged"]
    ):
        raise ValueError("Winner/source/accepted-model binding failed")
    anchor = repo / "artifacts/m33-primary-relations-20261008-v5"
    if (
        sha(anchor / "best.pt") != ANCHOR
        or sha(anchor / "frozen-calibration.json") != POLICY
    ):
        raise ValueError("Local accepted model changed")
    for name in ("dataset.json", "pixels.npz"):
        if sha(data / name) != sha(root / "preparation-replay-v2" / name):
            raise ValueError("Preparation replay differs")
    write_json(
        root / "preparation-replay-receipt.json",
        {
            "status": "BYTE_IDENTICAL_PREPARATION_REPLAY",
            "dataset_sha256": sha(data / "dataset.json"),
            "pixels_sha256": sha(data / "pixels.npz"),
            "script_sha256": sha(repo / "scripts/m33_objects_expand_prepare.py"),
            "limits": "Preparation only, not GPU training reproducibility or independent labels.",
        },
    )
    registry = load(data / "image-registry.json")
    fresh = [
        r
        for r in registry
        if not r.get("parent") and r.get("role") != "SHARED_CONSTANT_CONTROL"
    ]
    artwork = [r for r in fresh if r.get("publisher")]
    development = load(
        Path(selection["winner"]["candidate_path"]) / "development-report.json"
    )
    best = next(
        r for r in development["history"] if r["step"] == development["best_step"]
    )
    value = {
        "schema": 1,
        "focused_tests": {
            "passed": 270,
            "skipped": 2,
            "log_sha256": sha(test_log),
            "skip_reason": "Project venv lacks pdfplumber; unrelated PDF tests skipped.",
        },
        "date": "2026-10-09",
        "status": report["status"],
        "training_host": "karina",
        "scope": "Eight object names, own weights; bounded RU/EN prompts and Russian answers.",
        "data": {
            "new_admitted_images": len(fresh),
            "new_sketches": len(fresh) - len(artwork),
            "new_illustrations": len(artwork),
            "counts": {s: len(r) for s, r in dataset["records"].items()},
            "dataset_sha256": sha(data / "dataset.json"),
            "pixels_sha256": sha(data / "pixels.npz"),
            "registry_path": str(data / "image-registry.json"),
            "registry_sha256": sha(data / "image-registry.json"),
            "lineage": load(root / "preparation-lineage.json"),
            "old_final_role": "KNOWN_REGRESSION_NEVER_TRAINING",
            "OpenMoji_role": "FINAL_ONLY_HELD_OUT_STYLE",
        },
        "selection": selection,
        "development_raw_not_safe_policy": best["object_dev"],
        "training_peak_cuda_allocated_bytes": development["peak_cuda_allocated_bytes"],
        "checkpoint_bytes": (experiment / "best.pt").stat().st_size,
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "report_path": str(experiment / "report.json"),
        "report_sha256": sha(experiment / "report.json"),
        "object_gate": report["object_gate"],
        "regression_gate": report["regression_gate"],
        "production_admitted": False,
        "fresh_final": report["tests"]["object_final"],
        "threshold": report["thresholds"]["object"],
        "calibration_grid": diagnostic["grid"],
        "calibration_raw_not_safe_policy": diagnostic["raw_consensus"],
        "retention_gates": report["retention_gates"],
        "domain_diagnostics": load(root / "domain-diagnostics.json"),
        "arithmetic_audit": audit,
        "accepted_checkpoint_sha256": ANCHOR,
        "accepted_policy_sha256": POLICY,
        "accepted_model_unchanged_locally_and_remotely": True,
        "parent_archive_commit": PARENT,
        "limits": [
            "Curator saw categories; this is not an independent blind semantic exam.",
            "Held-out publisher and detected families do not prove exhaustive artist/semantic independence.",
            "Abstention and zero errors are not mastery; all original safety gates remain.",
            "Augmentations are training views, not independent new examples.",
            "Photos, definitions, broad language understanding, all textbooks and M34 not trained.",
            "Outside-scope examples do not teach their names. Accepted working model not replaced.",
        ],
    }
    output = repo / "learning_materials/visual_lexicon/objects_diversity_result.json"
    if output.exists():
        raise ValueError("Existing diversity result must remain immutable")
    write_json(output, value)
    return {
        "output": str(output),
        "sha256": sha(output),
        "object_gate": value["object_gate"],
    }


def archive(root, repo, output):
    output.mkdir(exist_ok=False)
    sources = []
    for name in (
        "raw-proposals",
        "illustrations",
        "prepared-v1",
        "development-v1",
        "source-capsule-v1.tgz",
    ):
        source = root / name
        sources.extend(
            (p.relative_to(root).as_posix(), p)
            for p in (source.rglob("*") if source.is_dir() else [source])
            if p.is_file()
        )
    sources.extend((p.name, p) for p in root.glob("*.json"))
    sources.append(("focused-regression.log", root / "focused-regression.log"))
    for name in ("objects_diversity_review.json", "objects_diversity_result.json"):
        sources.append(
            ("catalogue/" + name, repo / "learning_materials/visual_lexicon" / name)
        )
    for name in ("best.pt", "frozen-calibration.json"):
        sources.append(
            (
                "accepted-anchor/" + name,
                repo / "artifacts/m33-primary-relations-20261008-v5" / name,
            )
        )
    course = bundle(output / "diversity-course-evidence.zip", sources)
    publication = root / "publication"
    evidence = bundle(
        output / "publication-evidence.zip",
        [
            (p.relative_to(publication).as_posix(), p)
            for p in publication.rglob("*")
            if p.is_file()
            and p.name != "visual_lexicon.xlsx"
            and not p.name.endswith(".inspect.ndjson")
        ],
    )
    write_json(
        output / "backup-manifest.json",
        {
            "schema": 1,
            "parent_archive_commit": PARENT,
            "object_gate": load(
                repo / "learning_materials/visual_lexicon/objects_diversity_result.json"
            )["object_gate"],
            "production_admitted": False,
            "restore_root": str(root),
            "bundles": [course, evidence],
            "workbook_sha256": sha(publication / "visual_lexicon.xlsx"),
            "accepted_checkpoint_sha256": ANCHOR,
            "accepted_policy_sha256": POLICY,
            "restore_notes": "Restore bundles to restore_root; parent Git backup restores old datasets/source roots. XLSX and current scripts are separate Git blobs. Source capsule is exact training source; post-training tools are versioned separately. Historical absolute paths require remapping elsewhere.",
        },
    )
    return {
        "bundles": [
            {k: b[k] for k in ("file", "sha256", "bytes")} for b in (course, evidence)
        ]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("result", "archive"))
    for name in ("root", "repo"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            result(args.root, args.repo)
            if args.mode == "result"
            else archive(args.root, args.repo, args.output)
        )
    )

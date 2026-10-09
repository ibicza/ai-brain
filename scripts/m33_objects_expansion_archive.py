"""Seal measured expansion results and roundtrip-verified, restorable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import verify

PARENT = "07dc1ef3757f4ab62b8ae24da6fb0749b45e94c1"
ANCHOR = "a4a168a362f6afb20b9dc579ad91c47ca725ab0cbadb6a556a3d6e257e6c1fae"
POLICY = "21529d9cfd6e0b71f0fd58b6694dd3d32b7d680fd91d7bb002491c9c635591f6"


def result(root, repo):
    experiment = root / "development-v2/final-evaluation"
    data = root / "prepared-v1"
    audit = verify(experiment, data)
    report = json.loads((experiment / "report.json").read_text())
    selection = json.loads((root / "development-v2/selection-frozen.json").read_text())
    dataset = json.loads((data / "dataset.json").read_text())
    diagnostic = json.loads((experiment / "calibration-diagnostics.json").read_text())
    if diagnostic["script_sha256"] != sha(
        repo / "scripts/m33_objects_calibration_diagnostics.py"
    ):
        raise ValueError("Remote diagnostic script differs from saved source")
    winner = selection["winner"]
    development = json.loads(
        (Path(winner["candidate_path"]) / "development-report.json").read_text()
    )
    best = next(
        r for r in development["history"] if r["step"] == development["best_step"]
    )
    for name in ("dataset.json", "pixels.npz"):
        if sha(data / name) != sha(root / "preparation-replay-v2" / name):
            raise ValueError("Current preparation did not replay byte-identically")
    reproduction = {
        "status": "BYTE_IDENTICAL_PREPARATION_REPLAY",
        "dataset_sha256": sha(data / "dataset.json"),
        "pixels_sha256": sha(data / "pixels.npz"),
        "preparation_script_sha256": sha(
            repo / "scripts/m33_objects_expand_prepare.py"
        ),
        "limits": "Data preparation replay only, not GPU training reproducibility or label independence.",
    }
    write_json(root / "preparation-replay-receipt.json", reproduction)
    anchor = repo / "artifacts/m33-primary-relations-20261008-v5"
    if (
        sha(anchor / "best.pt") != ANCHOR
        or sha(anchor / "frozen-calibration.json") != POLICY
    ):
        raise ValueError("Accepted anchor/policy changed")
    transfer = json.loads(
        (root / "v2-post-diagnostic-transfer-receipt.json").read_text()
    )
    if (
        not transfer["accepted_checkpoint_unchanged"]
        or not transfer["accepted_policy_unchanged"]
    ):
        raise ValueError("Remote accepted model changed")
    value = {
        "schema": 1,
        "date": "2026-10-09",
        "status": report["status"],
        "training_host": "karina",
        "scope": "Eight visually curated schematic object labels; bounded RU/EN question templates, Russian name answers. Own inherited weights, no external pretrained model.",
        "data": {
            "new_proposals": 1920,
            "visually_excluded": 541,
            "new_admitted_drawings": 1379,
            "counts": {s: len(r) for s, r in dataset["records"].items()},
            "dataset_sha256": sha(data / "dataset.json"),
            "pixels_sha256": sha(data / "pixels.npz"),
            "registry_path": str(data / "image-registry.json"),
            "registry_sha256": sha(data / "image-registry.json"),
            "new_negative_categories": 12,
            "old_final_role": "KNOWN_REGRESSION_NEVER_TRAINING",
        },
        "selection": selection,
        "development_best_step_raw_stats_not_safe_policy": best["object_dev"],
        "training_peak_cuda_allocated_bytes": development["peak_cuda_allocated_bytes"],
        "checkpoint_bytes": (experiment / "best.pt").stat().st_size,
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "report_path": str(experiment / "report.json"),
        "report_sha256": sha(experiment / "report.json"),
        "object_gate": report["object_gate"],
        "regression_gate": report["regression_gate"],
        "production_admitted": False,
        "fresh_final": report["tests"]["object_final"],
        "calibration_grid": diagnostic["grid"],
        "calibration_raw_consensus_not_safe_policy": diagnostic["raw_consensus"],
        "threshold": report["thresholds"]["object"],
        "retention_gates": report["retention_gates"],
        "accepted_checkpoint_sha256": ANCHOR,
        "accepted_policy_sha256": POLICY,
        "accepted_model_unchanged_locally_and_remotely": True,
        "arithmetic_audit": audit,
        "parent_archive_commit": PARENT,
        "limits": [
            "No independent blind semantic labeling exam; curator saw source categories.",
            "Fresh control families exclude prior owners and detected pixel/mirror/coarse-mask duplicates, not every possible semantic or artist overlap.",
            "Object threshold absent: grid produced fewer than 50 accepted zero-error calibration answers. All final object answers abstain; zero errors is not mastery.",
            "Seven candidates differ in size, normalization and learning rate; winner is not causal proof that increasing size alone helps.",
            "Photos, word definitions, general bilingual understanding, all textbook objects and M34 were not trained.",
            "Twelve negative categories mean outside this eight-name answer scope, not acquisition of those twelve names.",
        ],
        "next_iteration": "Improve independently curated real illustrations and hard negatives, then freeze development selection and evaluate new untouched families; do not lower safety gates or reuse this final as fresh.",
    }
    output = repo / "learning_materials/visual_lexicon/objects_expansion_result.json"
    if output.exists():
        raise ValueError("Existing expansion result must remain immutable")
    write_json(output, value)
    return {
        "output": str(output),
        "sha256": sha(output),
        "object_gate": value["object_gate"],
    }


def bundle(target, sources):
    manifest = []
    with ZipFile(target, "x", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, source in sorted(sources):
            before = sha(source)
            archive.write(source, relative)
            if sha(source) != before:
                raise ValueError("Source changed during backup")
            manifest.append(
                {"path": relative, "sha256": before, "bytes": source.stat().st_size}
            )
    with ZipFile(target) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(manifest):
            raise ValueError("Corrupt or duplicated archive")
        for item in manifest:
            with archive.open(item["path"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError("Archive roundtrip mismatch")
    if target.stat().st_size >= 100_000_000:
        raise ValueError("Evidence exceeds ordinary Git blob limit")
    return {
        "file": target.name,
        "sha256": sha(target),
        "bytes": target.stat().st_size,
        "files": manifest,
    }


def archive(root, repo, output):
    output.mkdir(exist_ok=False)
    names = [
        "raw-proposals",
        "prepared-v1",
        "development-v1",
        "development-v2",
        "source-capsule-v1.tgz",
        "source-capsule-v2.tgz",
    ]
    sources = []
    for name in names:
        source = root / name
        sources.extend(
            (p.relative_to(root).as_posix(), p)
            for p in (source.rglob("*") if source.is_dir() else [source])
            if p.is_file()
        )
    sources.extend((p.name, p) for p in root.glob("*.json"))
    for name in ("objects_expansion_review.json", "objects_expansion_result.json"):
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
    course = bundle(output / "expansion-course-evidence.zip", sources)
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
    manifest = {
        "schema": 1,
        "parent_archive_commit": PARENT,
        "object_gate": False,
        "production_admitted": False,
        "restore_root": str(root),
        "bundles": [course, evidence],
        "workbook_sha256": sha(publication / "visual_lexicon.xlsx"),
        "accepted_checkpoint_sha256": ANCHOR,
        "accepted_policy_sha256": POLICY,
        "restore_notes": "Restore both bundles at restore_root. Restore prior raw source root from parent Git archive objects-block1-20261009. Main catalogue XLSX, exports and current scripts are separate Git blobs. Immutable capsules retain exact training source; accepted-anchor contains prior working model. Absolute paths in registry are historical and need root remapping on another machine.",
    }
    write_json(output / "backup-manifest.json", manifest)
    return {
        "bundles": [
            {k: b[k] for k in ("file", "sha256", "bytes")} for b in manifest["bundles"]
        ]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("result", "archive"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            result(args.root, args.repo)
            if args.mode == "result"
            else archive(args.root, args.repo, args.output)
        )
    )

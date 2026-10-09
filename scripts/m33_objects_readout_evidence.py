"""Development-only visual-readout evidence, never fresh-exam or admission proof."""

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path
from xml.etree import ElementTree as ET

import torch
from m33_objects_context_probe_report import audit
from m33_objects_data import sha, write_json
from m33_objects_readout_remote import DATA, WARM
from m33_objects_topup_evidence import bundle_parts, record_once
from m33_objects_transfer_verify import ACCEPTED, HOST, KEY, POLICY_SHA, PREVIOUS_SHA
from m33_primary_objects_pilot import verify_inherited
from m33_verify_objects_evidence import selected, statistics

from ai_brain.training import primary_objects as obj

REMOTE = "/home/ibicza/ai-brain/runs/m33-primary-objects-readout-20261009-v1"
PARENT = "eee4ec3e7ea99bc788c4be8feb9915b56fb5c46b"
NAMES = ("baseline_native", "baseline_canvas", "readout_native", "readout_canvas")
WORKBOOK = "40bef10fbedb65f61538bb8b2c7a7d12e415ffb07b092fe48d107bdadedd7730"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_transfer(root):
    capsule = root / "source-capsule-v1.tgz"
    expected = {
        REMOTE + "/capsule.tgz": sha(capsule),
        REMOTE + "/warm.pt": WARM,
        REMOTE + "/previous.pt": PREVIOUS_SHA,
        REMOTE + "/previous-policy.json": POLICY_SHA,
        ACCEPTED + "/best.pt": PREVIOUS_SHA,
        ACCEPTED + "/frozen-calibration.json": POLICY_SHA,
    }
    with tarfile.open(capsule) as archive:
        manifest_bytes = archive.extractfile("source-manifest.json").read()
        manifest = json.loads(manifest_bytes)
        expected[REMOTE + "/source-manifest.json"] = hashlib.sha256(
            manifest_bytes
        ).hexdigest()
        for row in manifest["files"]:
            with archive.extractfile(row["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Frozen capsule corrupt")
            expected[REMOTE + "/" + row["file"]] = row["sha256"]
    retrieved = []
    for name in (
        "development-v1",
        "selection-development-only.json",
        "dev-photo-diagnostic.json",
        "dev-photo-arithmetic-audit.json",
        "remote-tests.xml",
        "remote-tests-predependency.xml",
        "environment.json",
        "post-prompt-diagnostic.py",
        "prompt-dev-records.json.gz",
        "prompt-dev-diagnostic.json",
    ):
        path = root / name
        for file in path.rglob("*") if path.is_dir() else [path]:
            if file.is_file():
                expected[REMOTE + "/" + file.relative_to(root).as_posix()] = sha(file)
                retrieved.append(file)
    code = "import sys,json,hashlib,pathlib; paths=json.load(sys.stdin); print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}))"
    response = subprocess.run(
        [
            "ssh",
            "-i",
            KEY,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            HOST,
            "/home/ibicza/ai-brain/.venv/bin/python -c " + shlex.quote(code),
        ],
        input=json.dumps(list(expected)),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=60,
    )
    if json.loads(response.stdout) != expected:
        raise ValueError("Remote source, outputs or protected weights differ")
    receipt = {
        "status": "EXACT_REMOTE_BYTES_VERIFIED",
        "source_files": len(manifest["files"]),
        "retrieved_files": len(retrieved),
        "accepted_core_unchanged": True,
        "accepted_policy_unchanged": True,
        "capsule_sha256": sha(capsule),
        "remote_root": REMOTE,
        "files": expected,
    }
    record_once(root / "transfer-receipt.json", receipt)
    return receipt


def seal(root, repo, data):
    if sha(data / "dataset.json") != DATA or sha(root / "warm.pt") != WARM:
        raise ValueError("Frozen source data/warm anchor differs")
    if sha(repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx") != WORKBOOK:
        raise ValueError("Canonical workbook changed; preserve it")
    source = torch.load(
        repo / "artifacts/m33-primary-relations-20261008-v5/best.pt",
        weights_only=True,
        map_location="cpu",
    )
    if (
        sha(repo / "artifacts/m33-primary-relations-20261008-v5/best.pt")
        != PREVIOUS_SHA
        or sha(
            repo / "artifacts/m33-primary-relations-20261008-v5/frozen-calibration.json"
        )
        != POLICY_SHA
    ):
        raise ValueError("Accepted local core changed")
    reports = {}
    for name in NAMES:
        candidate = root / "development-v1" / name
        report, protocol = (
            load(candidate / "development-report.json"),
            load(candidate / "protocol.json"),
        )
        config = protocol["config"]
        if (
            report["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
            or report["production_admitted"]
            or not report["inherited_tensors_byte_preserved"]
            or report["protocol_sha256"] != sha(candidate / "protocol.json")
            or report["checkpoint_sha256"] != sha(candidate / "best.pt")
            or config["steps"] != 10000
            or config["round_id"] != 10971
            or config["learning_rate"] != 0.00003
            or protocol["warm_start_sha256"] != WARM
            or report["dataset_sha256"] != DATA
            or config["object_readout_adapter"] != name.startswith("readout")
            or config["background_augmentation"] != name.endswith("canvas")
            or report["best_dev_loss"] != min(r["dev_loss"] for r in report["history"])
            or any(
                (candidate / n).exists()
                for n in (
                    "report.json",
                    "frozen-calibration.json",
                    "object-final-predictions.json",
                )
            )
        ):
            raise ValueError("Invalid predeclared development trial")
        model = obj.ObjectsModel.from_checkpoint(
            torch.load(candidate / "best.pt", weights_only=True, map_location="cpu")
        )
        verify_inherited(model, source["model"])
        reports[name] = {
            k: report[k]
            for k in (
                "best_step",
                "best_dev_loss",
                "parameters",
                "architecture",
                "checkpoint_sha256",
                "inherited_tensors_byte_preserved",
                "peak_cuda_allocated_bytes",
            )
        }
    selection = load(root / "selection-development-only.json")
    winner = min(reports, key=lambda n: (reports[n]["best_dev_loss"], n))
    if (
        selection["winner"]["name"] != winner
        or selection["winner"]["checkpoint_sha256"]
        != reports[winner]["checkpoint_sha256"]
    ):
        raise ValueError("Development selection binding differs")
    numeric = audit(
        data,
        root / "development-v1",
        root / "dev-photo-diagnostic.json",
        ("warm", *NAMES),
    )
    diagnostic = load(root / "dev-photo-diagnostic.json")
    if diagnostic["script_sha256"] != sha(root / "frozen-diagnostic-source.py"):
        raise ValueError("Saved diagnostic source binding differs")
    from m33_objects_prompt_diagnostic import audit as prompt_audit

    prompts = load(root / "prompt-dev-diagnostic.json")
    if prompts["script_sha256"] != sha(root / "post-prompt-diagnostic.py"):
        raise ValueError("Controlled prompt source binding differs")
    prompt_receipt = prompt_audit(
        data,
        root,
        root / "prompt-dev-records.json.gz",
        root / "prompt-dev-diagnostic.json",
    )
    observed = {}
    for name, value in diagnostic["candidates"].items():
        observed[name] = {
            mode: {
                "raw_not_safe_policy": value[mode]["raw_not_safe_policy"],
                "fixed_099_dev_only_not_admission": statistics(
                    [
                        dict(r, selected=selected(r["probabilities"], 0.99))
                        for r in value[mode]["records"]
                    ]
                ),
            }
            for mode in ("single_view", "five_view")
        }
    tests = {}
    for name in (
        "focused-tests-v2.xml",
        "remote-tests.xml",
        "model-contract-tests-v2.xml",
    ):
        suites = ET.parse(root / name).getroot().findall("testsuite")
        counts = {
            k: sum(int(s.get(k, 0)) for s in suites)
            for k in ("tests", "failures", "errors", "skipped")
        }
        if (
            counts["failures"]
            or counts["errors"]
            or counts["tests"] < (232 if name.startswith("focused") else 33)
        ):
            raise ValueError("Successful local/remote checks required")
        tests[name] = counts
    receipt = verify_transfer(root)
    output = (
        repo
        / "learning_materials/visual_lexicon/objects_readout_development_result.json"
    )
    result = {
        "schema": 1,
        "date": "2026-10-09",
        "status": "DEVELOPMENT_COMPLETE_NOT_FINAL_OR_PRODUCTION",
        "production_admitted": False,
        "fresh_final_exam_performed": False,
        "scope": "Own eight-object visual readout and intact-frame padding augmentation.",
        "data_sha256": DATA,
        "trials": reports,
        "winner": selection["winner"],
        "dev_photo_diagnostics": observed,
        "arithmetic_audit": numeric,
        "controlled_prompt_diagnostic": prompts,
        "controlled_prompt_arithmetic_audit": prompt_receipt,
        "tests": tests,
        "transfer": {k: v for k, v in receipt.items() if k != "files"},
        "canonical_workbook_unchanged_sha256": WORKBOOK,
        "environment": load(root / "environment.json"),
        "limits": "Curated known development, not blind source-label verification. Same corpus/seed/budget does not prove identical minibatches: extra initialization/augmentation can consume RNG differently. Raw agreement or zero dev errors does not certify safety on unseen scenes. Padding augmentation is not foreground segmentation/background replacement. Prior final is now known; no calibration/final inference here and no workbook test percentages replaced with dev scores.",
        "next": "Use development evidence to choose a candidate or revise the visual branch, then a separately sourced author/scene-disjoint final with frozen calibration and unchanged safety gates. Keep working production core untouched.",
    }
    write_json(output, result)
    write_json(root / "development-result.json", result)
    return {"winner": winner, "result_sha256": sha(output), "observed": observed}


def archive(root, repo, output):
    sources = [
        (p, p.relative_to(root).as_posix())
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.name != "results.tgz"
    ]
    sources.append(
        (
            repo / "scripts/requirements-primary-vision.txt",
            "postprocessing/requirements-primary-vision.txt",
        )
    )
    parts = bundle_parts(output, sources)
    write_json(
        output / "backup-manifest.json",
        {
            "schema": 1,
            "parent_backup_commit": PARENT,
            "restore_root": str(root),
            "remote_root": REMOTE,
            "bundles": parts,
            "production_admitted": False,
            "restore_notes": "Extract parts under restore_root; source capsule contains exact model/training source and dataset arrays. Parent backup supplies photos, normalized image links, canonical workbook and accepted core. This stage performs known development only; old final is not fresh and workbook metrics remain historical.",
        },
    )
    return {"parts": len(parts), "bytes": sum(p["bytes"] for p in parts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seal", "archive"))
    for name in ("root", "repo"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            seal(args.root, args.repo, args.data)
            if args.mode == "seal"
            else archive(args.root, args.repo, args.output)
        )
    )

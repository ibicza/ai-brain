"""Seal five adaptive iterations and known-cohort regression without claiming blindness."""

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path
from xml.etree import ElementTree as ET

import torch
from m33_objects_context_probe_report import audit as dev_audit
from m33_objects_data import sha
from m33_objects_five_iterations import DATA, TRIALS, WARM
from m33_objects_topup_evidence import bundle_parts, record_once
from m33_objects_transfer_verify import ACCEPTED, HOST, KEY, POLICY_SHA, PREVIOUS_SHA
from m33_primary_objects_pilot import verify_inherited
from m33_verify_objects_evidence import selected, statistics, verify

from ai_brain.training import primary_objects as obj

REMOTE = "/home/ibicza/ai-brain/runs/m33-primary-objects-five-iterations-20261009-v1"
PARENT = "734df7b702fc8a894e986af81960ee7e4647a0be"
WORKBOOK = "40bef10fbedb65f61538bb8b2c7a7d12e415ffb07b092fe48d107bdadedd7730"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit_lineage(root, data):
    """Pure bookkeeping check: cannot certify source labels or semantic independence."""
    selection = load(root / "selection-development-only.json")
    anchor = load(root / "development-v1/initial-anchor-score.json")
    plan = load(root / "development-v1/plan.json")
    if (
        sha(data / "dataset.json") != DATA
        or plan["dataset_sha256"] != DATA
        or plan["warm_sha256"] != WARM
        or plan["trials"] != list(TRIALS)
        or selection["production_admitted"]
        or selection["fresh_acceptance_passed"]
        or selection["selection_used"] != "DEVELOPMENT_ONLY"
        or anchor["checkpoint_sha256"] != WARM
        or anchor["round_id"] != 10981
    ):
        raise ValueError("Five-iteration data/plan/selection changed")
    champion_sha, champion_score, champion_name = (
        WARM,
        anchor["best_dev_loss"],
        "initial_warm",
    )
    receipts = []
    for number, trial in enumerate(TRIALS, 1):
        name = trial["name"]
        candidate = root / "development-v1" / name
        protocol, report, receipt = (
            load(candidate / "protocol.json"),
            load(candidate / "development-report.json"),
            load(root / "development-v1" / (name + "-receipt.json")),
        )
        config = protocol["config"]
        if (
            receipt["iteration"] != number
            or receipt["trial"] != trial
            or receipt["warm_sha256"] != champion_sha
            or protocol["warm_start_sha256"] != champion_sha
            or receipt["champion_score_before"] != champion_score
            or report["checkpoint_sha256"] != sha(candidate / "best.pt")
            or report["protocol_sha256"] != sha(candidate / "protocol.json")
            or report["dataset_sha256"] != DATA
            or report["production_admitted"]
            or not report["inherited_tensors_byte_preserved"]
            or report["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
            or report["best_dev_loss"] != min(r["dev_loss"] for r in report["history"])
            or [r["step"] for r in report["history"]] != list(range(500, 10001, 500))
            or config["steps"] != 10000
            or config["round_id"] != 10981
            or config["learning_rate"] != 0.00003
            or not config["paired_object_training"]
            or any(
                config[k] != trial[k]
                for k in (
                    "consistency_weight",
                    "supervised_contrastive_weight",
                    "vicreg_weight",
                    "object_prompt_balancing",
                )
            )
            or config["object_readout_adapter"] != receipt["object_readout_adapter"]
            or any(
                (candidate / n).exists()
                for n in (
                    "report.json",
                    "frozen-calibration.json",
                    "object-final-predictions.json",
                )
            )
        ):
            raise ValueError("Iteration provenance/steps/objectives differ: " + name)
        diagnostic_path = root / (name + "-dev-photo.json")
        dev_audit(data, root / "development-v1", diagnostic_path, ("warm", name))
        diagnostic = load(diagnostic_path)["candidates"][name]
        rows = [
            dict(r, selected=selected(r["probabilities"], 0.99))
            for r in diagnostic["five_view"]["records"]
        ]
        stats = statistics(rows)
        classes = {
            label: statistics([r for r in rows if r["gold"] == label])
            for label in sorted({r["gold"] for r in rows if r["gold"] != "UNKNOWN"})
        }
        viable = (
            stats["false_assertions"] == 0
            and stats["answerable_recall"] >= 0.8
            and stats["unknown_recall"] >= 0.9
            and len(classes) == 8
            and all(
                v["accepted"] >= 5 and v["answerable_recall"] >= 0.8
                for v in classes.values()
            )
        )
        if (
            receipt["fixed_99_five_view_dev"] != stats
            or receipt["by_concept"] != classes
            or receipt["raw_single_view"]
            != diagnostic["single_view"]["raw_not_safe_policy"]
            or receipt["raw_five_view"]
            != diagnostic["five_view"]["raw_not_safe_policy"]
            or receipt["best_dev_loss"] != report["best_dev_loss"]
            or receipt["checkpoint_sha256"] != report["checkpoint_sha256"]
            or receipt["fresh_acceptance_passed"]
            or receipt["dev_screen_viable"] != viable
        ):
            raise ValueError("Iteration metrics changed: " + name)
        promoted = report["best_dev_loss"] < champion_score
        if receipt["promoted_by_development_loss"] != promoted:
            raise ValueError("Lineage promotion violated")
        if promoted:
            champion_sha, champion_score, champion_name = (
                report["checkpoint_sha256"],
                report["best_dev_loss"],
                name,
            )
        receipts.append(receipt)
    winner = selection["winner"]
    if (
        winner["checkpoint_sha256"] != champion_sha
        or winner["best_dev_loss"] != champion_score
        or winner["name"] != champion_name
        or selection["iterations"] != receipts
    ):
        raise ValueError("Frozen adaptive winner changed")
    return {
        "status": "FIVE_ITERATIONS_ARITHMETIC_LINEAGE_VERIFIED_NOT_BLIND",
        "training_steps": 50000,
        "iterations": receipts,
        "winner": winner,
    }


def transfer(root):
    expected = {
        REMOTE + "/capsule.tgz": sha(root / "source-capsule-v1.tgz"),
        REMOTE + "/warm.pt": WARM,
        REMOTE + "/previous.pt": PREVIOUS_SHA,
        REMOTE + "/previous-policy.json": POLICY_SHA,
        ACCEPTED + "/best.pt": PREVIOUS_SHA,
        ACCEPTED + "/frozen-calibration.json": POLICY_SHA,
    }
    with tarfile.open(root / "source-capsule-v1.tgz") as archive:
        source_blob = archive.extractfile("source-manifest.json").read()
        manifest = json.loads(source_blob)
        expected[REMOTE + "/source-manifest.json"] = hashlib.sha256(
            source_blob
        ).hexdigest()
        for row in manifest["files"]:
            with archive.extractfile(row["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Capsule corruption")
            expected[REMOTE + "/" + row["file"]] = row["sha256"]
    for p in (root / "remote-results").rglob("*"):
        if p.is_file():
            expected[
                REMOTE + "/" + p.relative_to(root / "remote-results").as_posix()
            ] = sha(p)
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
        raise ValueError("Remote source/results/accepted anchor bytes differ")
    receipt = {
        "status": "EXACT_REMOTE_SOURCE_RESULTS_AND_ACCEPTED_ANCHORS_VERIFIED",
        "source_files": len(manifest["files"]),
        "remote_root": REMOTE,
        "files": expected,
    }
    record_once(root / "transfer-receipt.json", receipt)
    return receipt


def seal(root, repo, data, archive):
    local = root / "remote-results"
    if sha(repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx") != WORKBOOK:
        raise ValueError("Canonical workbook changed; preserve it")
    anchor_path = repo / "artifacts/m33-primary-relations-20261008-v5/best.pt"
    if sha(anchor_path) != PREVIOUS_SHA:
        raise ValueError("Accepted local anchor changed")
    anchor = torch.load(anchor_path, weights_only=True, map_location="cpu")
    numeric = audit_lineage(local, data)
    for trial in TRIALS:
        checkpoint = torch.load(
            local / "development-v1" / trial["name"] / "best.pt",
            weights_only=True,
            map_location="cpu",
        )
        development = load(
            local / "development-v1" / trial["name"] / "development-report.json"
        )
        if (
            checkpoint["step"] != development["best_step"]
            or checkpoint["architecture"] != development["architecture"]
            or checkpoint["previous_sha256"] != PREVIOUS_SHA
            or checkpoint["compatible_legacy_vocabulary"] is not True
        ):
            raise ValueError("Saved checkpoint training boundary differs")
        model = obj.ObjectsModel.from_checkpoint(checkpoint)
        verify_inherited(model, anchor["model"])
    evaluation = local / "known-regression-evaluation"
    regression = verify(evaluation, data)
    if regression["checkpoint_sha256"] != numeric["winner"]["checkpoint_sha256"]:
        raise ValueError("Regression not bound to frozen development winner")
    from m33_objects_prompt_diagnostic import audit as prompt_audit

    prompt_receipt = prompt_audit(
        data,
        local,
        local / "prompt-dev-records.json.gz",
        local / "prompt-dev-diagnostic.json",
    )
    controlled_prompts = load(local / "prompt-dev-diagnostic.json")
    if controlled_prompts["script_sha256"] != sha(local / "post_prompt_diagnostic.py"):
        raise ValueError("Controlled prompt diagnostic source differs")
    counts = {}
    for path in (root / "focused-tests-v4.xml", local / "remote-tests.xml"):
        suites = ET.parse(path).getroot().findall("testsuite")
        value = {
            k: sum(int(s.get(k, 0)) for s in suites)
            for k in ("tests", "failures", "errors", "skipped")
        }
        if (
            value["failures"]
            or value["errors"]
            or value["tests"] < (236 if path.name.startswith("focused") else 23)
        ):
            raise ValueError("Passing local/remote tests required")
        counts[path.name] = value
    receipt = transfer(root)
    report = load(evaluation / "report.json")
    result = {
        "schema": 1,
        "date": "2026-10-09",
        "status": "FIVE_ITERATIONS_COMPLETED_NOT_PRODUCTION",
        "scope": "Own eight-object paired-view feature training; not general sight or M33 closure.",
        "production_admitted": False,
        "fresh_exam_performed": False,
        "arithmetic_audit": numeric,
        "known_regression_audit": regression,
        "known_regression_tests": report["tests"],
        "calibration_thresholds": report["thresholds"],
        "retention_gates": report["retention_gates"],
        "known_regression_status": report["status"],
        "tests": counts,
        "controlled_prompt_arithmetic_audit": prompt_receipt,
        "controlled_prompt_diagnostic": controlled_prompts,
        "visible_dev_error_review": load(
            repo / "learning_materials/visual_lexicon/objects_five_error_review.json"
        ),
        "data_sha256": DATA,
        "transfer_receipt_sha256": sha(root / "transfer-receipt.json"),
        "canonical_workbook_preserved_sha256": WORKBOOK,
        "accepted_core_preserved_sha256": PREVIOUS_SHA,
        "literature": load(local / "development-v1/plan.json")["literature"],
        "limits": "Five sequential adaptive development iterations are NOT independent exams. Known final reused once only after winner frozen, and reported only as regression. No next batch without fresh source acceptance. Labels remain nonblind curated. No threshold/gate weakening.",
    }
    record_once(root / "five-iterations-result.json", result)
    record_once(
        repo / "learning_materials/visual_lexicon/objects_five_iterations_result.json",
        result,
    )
    parts = [
        (p, p.relative_to(root).as_posix())
        for p in root.rglob("*")
        if p.is_file()
        and p.name
        not in ("results.tgz", "backup-isolated.index", "backup-push-receipt.json")
    ]
    bundles = bundle_parts(archive, parts)
    record_once(
        archive / "backup-manifest.json",
        {
            "schema": 1,
            "parent_backup_commit": PARENT,
            "status": result["status"],
            "result_sha256": sha(root / "five-iterations-result.json"),
            "bundles": bundles,
            "no_original_source_media_duplicate": True,
            "prepared_pixels_note": "Frozen source capsule retains prepared RGB96x96 training inputs; original source-media archive remains in the parent backup.",
            "parent_corpus_dataset_sha256": DATA,
            "source_files_verified": receipt["source_files"],
        },
    )
    return {
        "status": result["status"],
        "steps": numeric["training_steps"],
        "bundles": len(bundles),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "root", "data", "archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seal(args.root, args.repo, args.data, args.archive)))

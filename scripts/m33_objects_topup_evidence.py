"""Verify and seal this fresh-photo experiment, never activate its weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from m33_objects_data import sha, write_json
from m33_objects_transfer_verify import ACCEPTED, HOST, KEY, POLICY_SHA, PREVIOUS_SHA
from m33_verify_objects_evidence import verify

REMOTE = "/home/ibicza/ai-brain/runs/m33-primary-photo-topup-20261009-v1"
PARENT = "da360991d2950cf4ff3d8ada21ccb1ba15725f5d"
WARM_SHA = "f5d0c9b83d3b82ec512dc35ffe754338642178b7418f24de7b19574ea835205a"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def record_once(path, value):
    """Permit identical retries, never replace a differently bound receipt."""
    if path.exists():
        if load(path) != value:
            raise ValueError("Receipt differs; a fresh receipt path is required")
    else:
        write_json(path, value)


def transfer(root, repo, output=None):
    capsule = root / "training-source-v1.tgz"
    local = root / "full-training-v1"
    expected = {
        REMOTE + "/capsule.tgz": sha(capsule),
        REMOTE + "/warm.pt": WARM_SHA,
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
        for entry in manifest["files"]:
            with archive.extractfile(entry["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError("Frozen capsule entry differs")
            expected[REMOTE + "/" + entry["file"]] = entry["sha256"]
    retrieved = [p for p in sorted(local.rglob("*")) if p.is_file()]
    if not retrieved or not (local / "final-evaluation/report.json").is_file():
        raise ValueError("Completed retrieved final evidence required")
    for path in retrieved:
        remote_path = REMOTE + "/" + path.relative_to(local).as_posix()
        if remote_path in expected and expected[remote_path] != sha(path):
            raise ValueError("Retrieved source manifest differs")
        expected[remote_path] = sha(path)
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
        raise ValueError("Remote bytes or accepted anchors differ")
    anchor = repo / "artifacts/m33-primary-relations-20261008-v5"
    if (
        sha(anchor / "best.pt") != PREVIOUS_SHA
        or sha(anchor / "frozen-calibration.json") != POLICY_SHA
    ):
        raise ValueError("Local accepted anchors differ")
    receipt = {
        "status": "EXACT_FROZEN_TRANSFER_VERIFIED",
        "source_files": len(manifest["files"]),
        "retrieved_files": len(retrieved),
        "remote_root": REMOTE,
        "capsule_sha256": sha(capsule),
        "accepted_checkpoint_unchanged": True,
        "accepted_policy_unchanged": True,
        "files": expected,
    }
    record_once(output or root / "full-transfer-receipt.json", receipt)
    return receipt


def result(root, repo):
    output = repo / "learning_materials/visual_lexicon/objects_photo_topup_result.json"
    if output.exists():
        raise ValueError("Existing experiment result is immutable")
    full = root / "full-training-v1"
    report = load(full / "final-evaluation/report.json")
    selection_path = full / "selection-frozen.json"
    selection = load(selection_path)
    dataset = root / "prepared-v1"
    audit = verify(full / "final-evaluation", dataset)
    if report["checkpoint_sha256"] != selection["winner"][
        "checkpoint_sha256"
    ] or report["selection_receipt_sha256"] != sha(selection_path):
        raise ValueError("Frozen winner does not bind final evaluation")
    suites = ET.parse(root / "focused-tests-v3.xml").getroot().findall("testsuite")
    tests = {
        k: sum(int(s.get(k, 0)) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    if tests["tests"] < 219 or tests["failures"] or tests["errors"]:
        raise ValueError("Successful focused regression required")
    trials = {}
    for name in ("vision64", "vision128"):
        path = full / "development-v1" / name
        dev, protocol = (
            load(path / "development-report.json"),
            load(path / "protocol.json"),
        )
        if (
            dev["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
            or dev["production_admitted"]
            or not dev["inherited_tensors_byte_preserved"]
            or dev["checkpoint_sha256"] != sha(path / "best.pt")
            or dev["protocol_sha256"] != sha(path / "protocol.json")
            or protocol["config"]["steps"] != 10000
            or dev["best_dev_loss"] != min(r["dev_loss"] for r in dev["history"])
        ):
            raise ValueError("Invalid matched development trial")
        trials[name] = {
            k: dev[k]
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
    coverage = load(root / "photo-coverage-prepared-v1.json")
    if not coverage["ready"]:
        raise ValueError("Complete pretraining coverage required")
    receipt = transfer(root, repo, root / "full-transfer-final-receipt.json")
    publication = load(root / "publication/saved-xlsx-preservation-extended.json")
    if (
        not publication["all_other_cells_preserved"]
        or not publication["styles_and_native_features_preserved"]
    ):
        raise ValueError("Catalogue preservation evidence required")
    value = {
        "schema": 1,
        "date": "2026-10-09",
        "training_host": "karina",
        "status": report["status"],
        "object_gate": report["object_gate"],
        "production_admitted": False,
        "scope": "Eight object names, own weights, bounded RU/EN questions and Russian answers.",
        "new_curated_photos": 730,
        "new_proposals_reviewed_this_stage": 1419,
        "new_photos_admitted_this_stage": 475,
        "previous_untrained_photos": 255,
        "coverage": coverage,
        "trials": trials,
        "winner": selection["winner"],
        "dataset_sha256": sha(dataset / "dataset.json"),
        "pixels_sha256": sha(dataset / "pixels.npz"),
        "image_registry_sha256": sha(dataset / "image-registry.json"),
        "tests": report["tests"],
        "thresholds": report["thresholds"],
        "focused_tests": tests,
        "arithmetic_audit": audit,
        "domain_diagnostic": load(full / "domain-diagnostic.json"),
        "post_freeze_dev_photo_diagnostic_not_safe_policy": load(
            full / "post-dev-photo-diagnostic.json"
        ),
        "next": "Improve own visual representation and scene/background invariance on training/development only, retaining the accepted seven-skill core. Width doubling alone did not win. This final is now known and may only become regression; another final requires fresh held-out sources and predeclared author/scene groups. Do not weaken abstention thresholds or claim general vocabulary/textbook mastery.",
        "transfer": {k: v for k, v in receipt.items() if k != "files"},
        "catalogue": publication,
        "accepted_core_sha256": PREVIOUS_SHA,
        "accepted_policy_sha256": POLICY_SHA,
        "limits": "Visually curated nonblind labels; independent arithmetic/hash checks are not a blind semantic exam. Declared artist/author and RGB grouping does not prove all scene/session independence. File-specific thumbnail licences and attribution retained, not blanket depicted-work rights. No threshold weakening or final-based candidate selection. Strict M33 remains unclosed; textbook reading and all vocabulary meanings are not learned.",
    }
    write_json(output, value)
    return {
        "output": str(output),
        "sha256": sha(output),
        "object_gate": report["object_gate"],
    }


def bundle_parts(destination, sources, limit=40 * 1024 * 1024):
    """CRC and full hash roundtrip of bounded parts; refuse ambiguous restore paths."""
    if destination.exists():
        raise ValueError("Fresh archive directory required")
    entries = sorted(sources, key=lambda row: row[1])
    names = [n for _, n in entries]
    if len(set(names)) != len(names) or any(
        not n or "\\" in n or n.startswith("/") or ".." in n.split("/") for n in names
    ):
        raise ValueError("Unsafe or duplicate archive member")
    if any(p.stat().st_size > limit for p, _ in entries):
        raise ValueError("Individual artifact exceeds part limit")
    destination.mkdir(parents=True)
    groups, current, size = [], [], 0
    for path, name in entries:
        count = path.stat().st_size
        if current and size + count > limit:
            groups.append(current)
            current, size = [], 0
        current.append((path, name))
        size += count
    if current:
        groups.append(current)
    bundles = []
    for number, group in enumerate(groups, 1):
        target = destination / f"evidence-{number:02d}.zip"
        records = []
        with zipfile.ZipFile(
            target,
            "x",
            zipfile.ZIP_DEFLATED,
            compresslevel=6,
            strict_timestamps=False,
        ) as archive:
            for path, name in group:
                digest = sha(path)
                archive.write(path, name)
                if sha(path) != digest:
                    raise ValueError("Archive input changed")
                records.append(
                    {"file": name, "sha256": digest, "bytes": path.stat().st_size}
                )
        with zipfile.ZipFile(target) as archive:
            if archive.testzip():
                raise ValueError("Archive CRC mismatch")
            for entry in records:
                with archive.open(entry["file"]) as stream:
                    if (
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        != entry["sha256"]
                    ):
                        raise ValueError("Archive hash roundtrip mismatch")
        if target.stat().st_size >= 50_000_000:
            raise ValueError("Archive exceeds ordinary Git advisory blob size")
        bundles.append(
            {
                "file": target.name,
                "sha256": sha(target),
                "bytes": target.stat().st_size,
                "entries": records,
            }
        )
    return bundles


def archive(root, repo, output):
    sources = [
        (p, p.relative_to(root).as_posix())
        for p in root.rglob("*")
        if p.is_file()
        and not p.is_relative_to(output)
        and not p.name.endswith(".inspect.ndjson")
        and "__pycache__" not in p.parts
        and p.name not in ("prepared.json", "capacity-results.tgz", "full-results.tgz")
    ]
    # The actual XLSX plus seven exports preserve all rows; the 51 MB authoring
    # intermediate is deliberately not a restore dependency.
    sources.extend(
        (repo / "learning_materials/visual_lexicon" / name, "catalogue/" + name)
        for name in (
            "objects_photo_topup_review.json",
            "objects_photo_targeted_review.json",
            "objects_photo_topup_queries.json",
            "objects_photo_topup_cohort_caps.json",
            "objects_photo_targeted_queries.json",
            "objects_photo_targeted_cohort_caps.json",
            "objects_photo_topup_result.json",
        )
    )
    bundles = bundle_parts(output, sources)
    manifest = {
        "schema": 1,
        "parent_backup_commit": PARENT,
        "restore_root": str(root),
        "remote_root": REMOTE,
        "bundles": bundles,
        "production_admitted": False,
        "restore_notes": "Extract parts under restore_root; catalogue/* correspond to repo files. Parent backup supplies old corpus/source roots and accepted core. Absolute paths require remapping on another host. Authoring prepared.json is excluded; saved XLSX and seven verified exports retain all authoritative records. Exact training source capsules are included; current postprocessing code is in the same Git backup.",
    }
    write_json(output / "backup-manifest.json", manifest)
    return {
        "parts": len(bundles),
        "bytes": sum(b["bytes"] for b in bundles),
        "manifest_sha256": sha(output / "backup-manifest.json"),
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

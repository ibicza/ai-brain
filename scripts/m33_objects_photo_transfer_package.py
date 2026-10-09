"""Seal the dev-only photo-transfer stage and restorable evidence, without promotion."""

import argparse
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from m33_objects_context_probe_report import audit
from m33_objects_data import sha, write_json
from m33_objects_illustrations import normalized
from m33_objects_photo_prepare import reviewed_rows

REMOTE = "/home/ibicza/ai-brain/runs/m33-primary-photo-transfer-20261009-v1"
PARENT_COMMIT = "f43abf8c4bfb315f97e19f5322014f56b9a828b0"
PREVIOUS_SHA = "a4a168a362f6afb20b9dc579ad91c47ca725ab0cbadb6a556a3d6e257e6c1fae"
POLICY_SHA = "21529d9cfd6e0b71f0fd58b6694dd3d32b7d680fd91d7bb002491c9c635591f6"


def transfer(repo, root):
    capsule = root / "context-probe-source-v1.tgz"
    with tarfile.open(capsule) as archive:
        manifest = json.load(archive.extractfile("source-manifest.json"))
        for entry in manifest["files"]:
            if (
                hashlib.file_digest(
                    archive.extractfile(entry["file"]), "sha256"
                ).hexdigest()
                != entry["sha256"]
            ):
                raise ValueError("Local frozen capsule entry changed")
    program = f"""
import hashlib,json
from pathlib import Path
root=Path({REMOTE!r})
def sha(p):
    with p.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
manifest=json.loads((root/'source-manifest.json').read_text())
sources={{r['file']:sha(root/r['file']) for r in manifest['files']}}
development={{p.relative_to(root/'development-probe-v1').as_posix():sha(p) for p in (root/'development-probe-v1').rglob('*') if p.is_file()}}
anchors={{n:sha(root/n) for n in ('capsule.tgz','warm.pt','previous.pt','previous-policy.json','post-context-report.py','context-photo-dev-diagnostics.json')}}
accepted=Path('/home/ibicza/ai-brain/runs/m33-primary-relations-20261008-v5/experiment')
anchors['accepted/best.pt']=sha(accepted/'best.pt')
anchors['accepted/frozen-calibration.json']=sha(accepted/'frozen-calibration.json')
print(json.dumps({{'sources':sources,'development':development,'anchors':anchors}}))
"""
    command = [
        "ssh",
        "-i",
        "C:/Users/artio/.ssh/id_ed25519_ai_brain_m192",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "ibicza@192.168.100.179",
        "/home/ibicza/ai-brain/.venv/bin/python -",
    ]
    response = subprocess.run(
        command, input=program, text=True, capture_output=True, check=True, timeout=60
    )
    remote = json.loads(response.stdout)
    if remote["sources"] != {r["file"]: r["sha256"] for r in manifest["files"]}:
        raise ValueError("Remote frozen source/data differs")
    local = {
        p.relative_to(root / "development-probe-v1").as_posix(): sha(p)
        for p in (root / "development-probe-v1").rglob("*")
        if p.is_file()
    }
    if remote["development"] != local:
        raise ValueError("Retrieved development evidence differs")
    expected = {
        "capsule.tgz": sha(capsule),
        "warm.pt": sha(root / "warm.pt"),
        "previous.pt": PREVIOUS_SHA,
        "previous-policy.json": POLICY_SHA,
        "accepted/best.pt": PREVIOUS_SHA,
        "accepted/frozen-calibration.json": POLICY_SHA,
        "post-context-report.py": sha(
            repo / "scripts/m33_objects_context_probe_report.py"
        ),
        "context-photo-dev-diagnostics.json": sha(
            root / "context-photo-dev-diagnostics.json"
        ),
    }
    if remote["anchors"] != expected:
        raise ValueError("Remote probe/accepted anchor/source differs")
    if (
        sha(repo / "artifacts/m33-primary-relations-20261008-v5/best.pt")
        != PREVIOUS_SHA
        or sha(
            repo / "artifacts/m33-primary-relations-20261008-v5/frozen-calibration.json"
        )
        != POLICY_SHA
    ):
        raise ValueError("Local accepted core/policy changed")
    result = {
        "status": "EXACT_FROZEN_TRANSFER_VERIFIED",
        "source_files": len(manifest["files"]),
        "retrieved_files": len(local),
        "capsule_sha256": sha(capsule),
        "anchors": expected,
        "remote_root": REMOTE,
    }
    write_json(root / "context-probe-transfer-receipt.json", result)
    return result


def package(repo, root, review, destination):
    if destination.exists():
        raise ValueError("Fresh archive destination required")
    destination.mkdir(parents=True)
    spec = json.loads(review.read_text(encoding="utf-8"))
    photos = root / "photos-v1"
    admitted, rejected, protected = reviewed_rows(photos, spec["photos"])
    acquisition = json.loads((photos / "acquisition.json").read_text(encoding="utf-8"))
    if len(acquisition["sources"]) != 644:
        raise ValueError("Reviewed proposal scope differs from this sealed stage")
    suites = ET.parse(root / "focused-tests.xml").getroot().findall("testsuite")
    tests = {
        k: sum(int(s.get(k, "0")) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    if tests["tests"] < 180 or tests["failures"] or tests["errors"]:
        raise ValueError("Successful focused regression evidence required")
    workbook_sha = sha(repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx")
    if (
        workbook_sha
        != "bfb8689c66f0d6241a3224581fcdf374912d2bf83cbcc78b530791fa58b08aa1"
    ):
        raise ValueError("Catalogue changed; preserve it and review before sealing")
    derivatives = root / "curated-v1"
    derivatives.mkdir()
    registry = []
    for row in admitted:
        path = derivatives / (row["source_id"].split("/")[-1] + ".png")
        image = normalized(row["source_file"])
        image.save(path)
        registry.append(
            row
            | {
                "image_path": str(path),
                "image_sha256": sha(path),
                "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                "training_admitted": False,
            }
        )
    write_json(root / "reviewed-media-registry.json", registry)
    transfer_receipt = transfer(repo, root)
    parent_data = root.parent / "objects-reliability-20261009/prepared-v1"
    arithmetic = audit(
        parent_data,
        root / "development-probe-v1",
        root / "context-photo-dev-diagnostics.json",
    )
    write_json(root / "context-probe-arithmetic-audit.json", arithmetic)
    readiness = json.loads(
        (root / "photo-coverage-v1.json").read_text(encoding="utf-8")
    )
    if readiness["review_sha256"] != sha(review) or readiness["reviewed_photos"] != len(
        admitted
    ):
        raise ValueError("Photo coverage binding differs")
    development = {}
    for name in ("local_only", "global_context"):
        trial = root / "development-probe-v1" / name
        report = json.loads((trial / "development-report.json").read_text())
        protocol = json.loads((trial / "protocol.json").read_text())
        if (
            report["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
            or report["production_admitted"]
            or not report["inherited_tensors_byte_preserved"]
            or report["checkpoint_sha256"] != sha(trial / "best.pt")
            or report["protocol_sha256"] != sha(trial / "protocol.json")
            or protocol["config"]["steps"] != 4000
            or report["best_dev_loss"] != min(r["dev_loss"] for r in report["history"])
        ):
            raise ValueError("Invalid short development evidence")
        development[name] = {
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
    result = {
        "schema": 1,
        "status": "DATA_EXPANSION_INCOMPLETE_DEV_PROBE_REJECTED_NOT_PRODUCTION",
        "production_admitted": False,
        "new_photos_trained": False,
        "focused_tests": tests,
        "new_photos": {
            "proposed": 644,
            "visually_curated": len(admitted),
            "visually_excluded": len(rejected),
            "review_sha256": sha(review),
            "acquisition_sha256": sha(photos / "acquisition.json"),
            "registry_sha256": sha(root / "reviewed-media-registry.json"),
            "readiness": readiness,
        },
        "development": development,
        "raw_dev_photo_diagnostics_not_safe_policy": arithmetic,
        "transfer": transfer_receipt,
        "accepted_core_sha256": PREVIOUS_SHA,
        "accepted_policy_sha256": POLICY_SHA,
        "canonical_workbook_unchanged_sha256": sha(
            repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx"
        ),
        "conclusion": "Neither continued baseline nor appended 27840-parameter global context beats the warm model on known sparse dev photo five-view recall (warm .40, local .20, context .30). No threshold lowered, final opened for selection, or production checkpoint changed. New data needs more positive/negative author/cohort coverage before a full photo-only iteration.",
        "limits": "4000-step known-development probe only, not independent blind semantics or M33 closure. Photo gold visually curated with source/owner visibility; artist aliases/session independence not exhaustive. Individual thumbnail rights retained; full originals not acquired; no blanket depicted-work permission. Existing catalogue learned statuses and M34 definitions unchanged.",
        "next": "Acquire focused foreground photos for missing classes/cohorts while excluding previous finished-round source IDs/authors; visually review and verify lineage/dedup and complete coverage before full matched training, frozen calibration, fresh final and regression.",
    }
    result_path = (
        repo / "learning_materials/visual_lexicon/objects_photo_transfer_result.json"
    )
    write_json(result_path, result)
    if any(sha(path) != digest for path, digest in protected.items()):
        raise ValueError("Photo evidence changed during packaging")
    bundles = []

    def bundle(kind, paths):
        groups, current, size = [], [], 0
        for path, name in sorted(paths, key=lambda item: item[1]):
            count = path.stat().st_size
            if count > 40 * 1024 * 1024:
                raise ValueError("Individual artifact exceeds bounded archive part")
            if current and size + count > 40 * 1024 * 1024:
                groups.append(current)
                current, size = [], 0
            current.append((path, name))
            size += count
        if current:
            groups.append(current)
        for part, group in enumerate(groups, 1):
            archive_path = destination / f"{kind}-{part:02d}.zip"
            entries = []
            with zipfile.ZipFile(
                archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                for path, name in group:
                    digest = sha(path)
                    archive.write(path, name)
                    if sha(path) != digest:
                        raise ValueError("Archive source changed")
                    entries.append(
                        {"file": name, "sha256": digest, "bytes": path.stat().st_size}
                    )
            with zipfile.ZipFile(archive_path) as archive:
                if archive.testzip():
                    raise ValueError("Archive CRC failure")
                for entry in entries:
                    if (
                        hashlib.file_digest(
                            archive.open(entry["file"]), "sha256"
                        ).hexdigest()
                        != entry["sha256"]
                    ):
                        raise ValueError("Archive roundtrip hash failure")
            if archive_path.stat().st_size >= 50_000_000:
                raise ValueError("Archive part exceeds GitHub advisory blob size")
            bundles.append(
                {
                    "file": archive_path.name,
                    "sha256": sha(archive_path),
                    "bytes": archive_path.stat().st_size,
                    "entries": entries,
                }
            )

    bundle(
        "photo-source-evidence",
        [
            (p, "photos-v1/" + p.relative_to(photos).as_posix())
            for p in photos.rglob("*")
            if p.is_file()
        ],
    )
    bundle(
        "development-and-review-evidence",
        [
            (p, p.relative_to(root).as_posix())
            for p in root.rglob("*")
            if p.is_file() and not p.is_relative_to(photos)
        ]
        + [
            (review, "review/" + review.name),
            (result_path, "review/" + result_path.name),
        ],
    )
    manifest = {
        "schema": 1,
        "parent_backup_commit": PARENT_COMMIT,
        "restore_root": str(root),
        "remote_root": REMOTE,
        "bundles": bundles,
        "result_sha256": sha(result_path),
        "limits": "Extract all parts under the restore root; review/* correspond to repository catalogue JSON. Prior parent backup supplies inherited dataset/accepted anchors. Absolute source paths require remapping on a different host. These are experiment/restoration artifacts, not production weights.",
    }
    write_json(destination / "backup-manifest.json", manifest)
    return {
        "status": result["status"],
        "curated": len(admitted),
        "archive_parts": [
            {k: b[k] for k in ("file", "bytes", "sha256")} for b in bundles
        ],
        "result_sha256": sha(result_path),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "root", "review", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.repo, args.root, args.review, args.output)))

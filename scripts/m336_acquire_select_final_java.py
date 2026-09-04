"""Acquire frozen source candidates and execute the M-33.6 selector exactly once."""

from __future__ import annotations

import argparse
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    load_disclosed_java_corpus_denylist,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.java_source_selector import (
    frozen_m336_final_source_selector_policy,
    m336_selector_receipt,
    select_final_java_sources,
    verify_m336_final_source_corpus,
)
from ai_brain.stage3.acquisition.maven_provenance import inspect_source_archive
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _safe_extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as opened:
        for info in opened.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or any(
                part in {"", ".", ".."} for part in path.parts
            ):
                raise ValueError("source archive contains an unsafe path")
            destination = target.joinpath(*path.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(opened.read(info))


def _license_receipt(
    archive: Path, family, acquired_at: str, *, disclosed_regression: bool = False
) -> dict:
    disclosed = load_disclosed_java_corpus_denylist()
    archive_hash = bytes_hash(archive.read_bytes())
    if archive_hash in disclosed["archive_hashes"] and not disclosed_regression:
        raise ValueError("final archive overlaps the permanent development denylist")
    inspection = inspect_source_archive(archive.read_bytes())
    exact = tuple(item for item in inspection.license_evidence if item.exact_match)
    license_path = exact[0].evidence_path if len(exact) == 1 else None
    license_hash = exact[0].raw_text_sha256 if len(exact) == 1 else None
    body = {
        "schema_version": 1,
        "family_id": family.family_id,
        "version": family.version,
        "source_archive_url": family.source_archive_url,
        "source_archive_sha256": archive_hash,
        "license_spdx": family.license_spdx,
        "license_archive_path": license_path,
        "license_bytes_hash": license_hash,
        "license_evidence_mode": (
            "EMBEDDED_EXACT_LICENSE" if license_path else "EXTERNAL_EVIDENCE_REQUIRED"
        ),
        "qualification_status": "ELIGIBLE" if license_path else "REVIEW_REQUIRED",
        "acquired_at": acquired_at,
    }
    return {**body, "receipt_hash": content_hash(body)}


def _copy_selected(selected, roots, target: Path) -> tuple[Path, ...]:
    root_map = tuple((name, path.resolve(strict=True)) for name, path in roots)
    copied = []
    for source in selected:
        matches = tuple(
            (name, root)
            for name, root in root_map
            if source.resolve().is_relative_to(root)
        )
        if len(matches) != 1:
            raise ValueError("selected source has ambiguous family ownership")
        family, root = matches[0]
        destination = target / family / source.resolve().relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(destination)
    return tuple(copied)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--f15-sha", required=True)
    parser.add_argument("--acquired-at", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disclosed-regression", action="store_true")
    args = parser.parse_args()
    if args.work_root.exists() or args.output.exists():
        raise FileExistsError("one-shot acquisition/selection target already exists")
    if len(args.f15_sha) != 40 or any(
        character not in "0123456789abcdef" for character in args.f15_sha
    ):
        raise ValueError("selector requires exact lowercase F15 SHA")
    policy = frozen_m336_final_source_selector_policy()
    args.work_root.mkdir(parents=True)
    archives_root = args.work_root / "archives"
    roots_root = args.work_root / "roots"
    archives_root.mkdir()
    roots = []
    receipts = []
    for family in policy.families:
        archive = archives_root / f"{family.family_id}-{family.version}-sources.jar"
        try:
            request = urllib.request.Request(
                family.source_archive_url,
                headers={"User-Agent": "ai-brain-m336-freeze/1"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                archive.write_bytes(response.read())
            receipt = _license_receipt(
                archive,
                family,
                args.acquired_at,
                disclosed_regression=args.disclosed_regression,
            )
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            receipts.append(
                {
                    "schema_version": 2,
                    "family_id": family.family_id,
                    "requirement": "OPTIONAL",
                    "qualification_status": "INELIGIBLE_PROVENANCE",
                    "reason": type(exc).__name__,
                }
            )
            continue
        receipts.append(receipt)
        if receipt["qualification_status"] != "ELIGIBLE":
            continue
        root = roots_root / family.family_id
        _safe_extract(archive, root)
        roots.append((family.family_id, root))
    selected = select_final_java_sources(
        tuple(roots), f13_sha=args.f15_sha, policy=policy
    )
    selector = m336_selector_receipt(policy, selected, tuple(roots), args.f15_sha)
    args.output.mkdir(parents=True)
    snapshot_root = args.output / "source_snapshots"
    copied = _copy_selected(selected, tuple(roots), snapshot_root)
    with tempfile.TemporaryDirectory(prefix="m336-corpus-verification-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        bundle = ingest_bundle(
            copied,
            bundle_id="m336-final-java",
            domain_tags=("java-api",),
            imported_at=args.acquired_at,
            store=store,
            source_root=snapshot_root,
        )
        index = index_java_bundle(bundle, store)
        census = verify_m336_final_source_corpus(bundle, index, policy)
    acquisition_body = {
        "schema_version": 1,
        "f15_sha": args.f15_sha,
        "policy_hash": policy.policy_hash,
        "receipts": tuple(receipts),
    }
    acquisition = {
        **acquisition_body,
        "manifest_hash": content_hash(acquisition_body),
    }
    overlap = {
        "schema_version": 1,
        "raw_source_overlap_count": census.raw_source_overlap_count,
        "canonical_source_overlap_count": census.canonical_source_overlap_count,
        "declaration_fingerprint_overlap_count": (
            census.declaration_fingerprint_overlap_count
        ),
        "normalized_similarity_overlap_count": (
            census.normalized_similarity_overlap_count
        ),
        "status": "PASS",
    }
    _write(args.output / "source_acquisition_receipts.json", acquisition)
    _write(args.output / "selector_receipt.json", selector)
    _write(args.output / "physical_census.json", asdict(census))
    _write(
        args.output / "source_overlap.json",
        {**overlap, "report_hash": content_hash(overlap)},
    )
    order = {
        "schema_version": 1,
        "selector_invocation_count": 1,
        "selection_observed_evaluator_result": False,
        "selection_observed_parser_accuracy": False,
        "f15_sha": args.f15_sha,
        "selector_receipt_hash": selector["receipt_hash"],
    }
    _write(
        args.output / "selection_execution.json",
        {**order, "receipt_hash": content_hash(order)},
    )


if __name__ == "__main__":
    main()

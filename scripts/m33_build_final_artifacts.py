"""Run the frozen generic M-33 compiler over already acquired inert snapshots."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.evidence import build_field_evidence
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.verification import (
    approve_exact_source_entailed,
    corroborate_source_entailed,
    verify_proposals,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument(
        "--selectors",
        type=Path,
        default=ROOT / "config/m33_final_source_selectors.json",
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("M-33 final artifact output must be absent")
    selectors = json.loads(args.selectors.read_text(encoding="utf-8"))
    summaries = []
    for sealed in selectors["sets"]:
        bundle_id = sealed["bundle_id"]
        source_root = args.sources / bundle_id
        source_paths = tuple(sorted(source_root.glob("*.txt")))
        if not source_paths:
            raise FileNotFoundError(f"no frozen snapshots for {bundle_id}")
        store = AcquisitionStore.open_or_initialize(
            args.output / "acquisition" / bundle_id
        )
        bundle = ingest_bundle(
            source_paths,
            bundle_id=bundle_id,
            domain_tags=tuple(sealed["domain_tags"]),
            imported_at=args.timestamp,
            version=sealed["version"],
            store=store,
        )
        segments = segment_bundle(bundle, store)
        segment_set = store.save_segments(bundle.bundle_hash, segments)
        parsed = propose_knowledge(bundle, segments, explicit_trust_stages=True)
        parsed_set = store.save_proposals(segment_set, parsed)
        evidence = build_field_evidence(bundle, segments, parsed, store)
        evidence_set = store.save_field_evidence(parsed_set, evidence)
        verified = verify_proposals(
            bundle, segments, parsed, store, field_evidence=evidence
        )
        verified = corroborate_source_entailed(verified, evidence)
        verified_set = store.save_proposals(segment_set, verified)
        approved = []
        approvals = []
        reviews = []
        for proposal in verified:
            if proposal.status.value not in {
                "SOURCE_ENTAILED",
                "CROSS_SOURCE_CORROBORATED",
            }:
                continue
            value, review, approval = approve_exact_source_entailed(
                proposal, timestamp=args.timestamp
            )
            approved.append(value)
            reviews.append(review)
            approvals.append(approval)
        approved_set = store.save_proposals(segment_set, tuple(approved))
        review_set = store.save_reviews(approved_set, tuple(reviews))
        pack = compile_provisional_pack(
            bundle,
            segments,
            tuple(approved),
            tuple(approvals),
            args.output / "packs" / bundle_id,
            domain_id=bundle_id,
            pack_version="1.0.0-m33",
            field_evidence=evidence,
        )
        pointers = {
            "bundle_hash": bundle.bundle_hash,
            "bundle_object": content_hash(asdict(bundle)),
            "segment_set": segment_set,
            "parsed_proposal_set": parsed_set,
            "field_evidence_set": evidence_set,
            "verified_proposal_set": verified_set,
            "approved_proposal_set": approved_set,
            "review_set": review_set,
        }
        summary = {
            "bundle_id": bundle_id,
            "document_count": len(bundle.documents),
            "segment_count": len(segments),
            "proposal_count": len(parsed),
            "field_evidence_count": len(evidence),
            "approved_count": len(approved),
            "pack_hash": pack.manifest.pack_content_hash,
            "pointers": pointers,
        }
        summaries.append({**summary, "summary_hash": content_hash(summary)})
    result = {
        "schema_version": 1,
        "timestamp": args.timestamp,
        "selectors_hash": content_hash(selectors),
        "bundles": summaries,
    }
    (args.output / "build_summary.json").write_text(
        canonical_json({**result, "build_hash": content_hash(result)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

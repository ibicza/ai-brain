from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import verify_bundle


def replay_acquisition(bundle, stored_segments, store) -> dict[str, object]:
    verify_bundle(bundle, store=store)
    rebuilt = segment_bundle(bundle, store)
    if tuple(asdict(item) for item in rebuilt) != tuple(
        asdict(item) for item in stored_segments
    ):
        raise ValueError("acquisition segmentation replay mismatch")
    body = {
        "bundle_hash": bundle.bundle_hash,
        "segment_hashes": tuple(item.segment_hash for item in rebuilt),
        "status": "REPLAYED",
    }
    return {**body, "replay_hash": content_hash(body)}

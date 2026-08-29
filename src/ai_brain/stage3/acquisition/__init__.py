"""Bounded deterministic Source-to-Knowledge Compiler."""

from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.identity import (
    detect_precompiler_identity_conflicts,
    match_java_source_location,
    parse_java_source_identities,
)
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.segmentation import (
    deduplicate_segments,
    segment_bundle,
    segment_bundle_with_report,
)
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.trust import evaluate_proposal_trust_gate

__all__ = [
    "compile_provisional_pack",
    "deduplicate_segments",
    "detect_precompiler_identity_conflicts",
    "evaluate_proposal_trust_gate",
    "ingest_bundle",
    "match_java_source_location",
    "parse_java_source_identities",
    "propose_knowledge",
    "segment_bundle",
    "segment_bundle_with_report",
]

"""Bounded deterministic Source-to-Knowledge Compiler."""

from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import ingest_bundle

__all__ = [
    "compile_provisional_pack",
    "ingest_bundle",
    "propose_knowledge",
    "segment_bundle",
]

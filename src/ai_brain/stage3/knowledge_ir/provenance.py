from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceReferences:
    fact_memory_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    source_hashes: tuple[str, ...] = ()
    derivation_hashes: tuple[str, ...] = ()
    source_chain_hash: str | None = None

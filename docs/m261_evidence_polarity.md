# M-26.1 Evidence Polarity

`SUPPORTS` and `CONTRADICTS` are separate channels from attachment through query
and rendering.

## Trusted Invariants

- Only approved SUPPORTS evidence contributes to support counts and freshness.
- Only active, non-model supporting sources contribute to independent support
  families and `CORROBORATED`.
- CONTRADICTS never increases support, corroboration, or support freshness.
- Approved contradiction remains visible as IDs, hashes, source references,
  freshness, and `CONTRADICTING_EVIDENCE_PRESENT`.
- Duplicate canonical claims merge attachments without changing relation polarity.
- Aggregate compatibility fields remain available but are not used by trust logic.

## Derived Answer State

`ClaimAnswer` exposes polarity-specific evidence/source IDs, hashes, citations,
trust tiers, independent-family counts, and freshness states. The immutable base
claim status is retained; active contradictory evidence sets
`evidence_conflict_state=CONTESTED` and answer `conflict_state=CONTESTED`.

With `include_evidence=false`, verbose citations are omitted but all evidence and
source IDs/hashes remain. The bundle declares `REFERENCES_ONLY` and emits
`EVIDENCE_DETAILS_OMITTED`.

## Audit And Verification

Attachments emit `CONTRADICTING_EVIDENCE_ATTACHED` and
`CLAIM_EVIDENCE_CONTESTED`. Integrity verification compares the immutable
evidence relation with `claim_evidence.relation`, verifies both hashes, and fails
closed on polarity tampering.

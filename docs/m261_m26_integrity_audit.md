# M-26 Integrity Audit

Baseline audited: `7ee89dd6d439a5f3d50612520789c26e42746ce9` on
`exp/stage2-factual-memory`.

| # | M-26 code path | Finding | M-26.1 disposition |
|---|---|---|---|
| 1 | `FactMemory.query`, `memory.py:1062` | `families` was derived from every attached evidence ID, regardless of relation. CONTRADICTS could create corroboration. | `_claim_evidence_by_polarity_at` and support-only family aggregation. |
| 2 | `FactMemory._claim_source_state`, `memory.py:1584` | Freshness used every evidence source. An active contradiction could mask retracted support. | `_claim_support_state` receives supporting sources only. |
| 3 | `FactMemory.approve_proposal`, `memory.py:628-647` | Reviewer type was an arbitrary string and trust depended on the exact string `"MODEL"`. | `ActorIdentityType` plus one fail-closed `_trusted_actor` guard. |
| 4 | `FactMemory.approve_proposal` and `_validate_proposal` | No source-kind rule prevented MODEL_INFERENCE-only support from becoming trusted after nominal human approval. | Approval binds `independent_non_model_support`; commit re-verifies it. |
| 5 | `FactMemory._claim_answer` -> `_claim_transaction_end`, `memory.py:1539,1609` | The first terminal event was returned without a `known_at` predicate, leaking future transaction end. | `transaction_interval_as_known_at` filters every status event by `known_at`. |
| 6 | `FactMemory.conflicts`, `memory.py:1184` | ConflictGroup stored one current status; there was no append-only resolution history or as-of projection. | `ConflictResolutionEvent`, `conflicts_at`, and event-derived projections. |
| 7 | `FactMemory._create_conflicts`, `memory.py:1435` | Conflict creation checked only `Cardinality.SINGLE`; `overlapping_intervals_permitted` was ignored. | SINGLE predicates return without conflict creation when overlap is permitted. |
| 8 | `FactMemory.make_query`, `memory.py:955`, and `_claim_answer`, `memory.py:1524` | `include_evidence` was hashed into the query but did not change answer construction. | FULL versus REFERENCES_ONLY provenance is explicit; IDs and hashes are always retained. |
| 9 | `FactMemory.get_source`, `memory.py:1168` | Returned the immutable creation payload, whose status remained ACTIVE after a status event. | `get_source` is current event-derived; `get_source_at` and `get_source_record` are explicit. |
| 10 | `runs/` at the baseline SHA | No committed M-26.1 local/Karina exact-SHA transcript existed. | M-26.1 requires both complete transcripts under `runs/m261_final_gate/`. |

The defects were local semantic failures inside the existing architecture. M-26.1
therefore keeps SQLite authority, immutable blobs, approval workflow, structured
queries, and the RuleMemory/SkillRegistry boundary unchanged.

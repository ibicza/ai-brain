# M-26 Provenance-Aware Bitemporal Factual Memory Report

## Outcome

**Outcome A: factual memory core works.**

M-26 provides typed claims, bitemporal history, provenance, explicit conflicts, hash-bound approvals, exact retrieval, evidence-bearing answers, transactional persistence, deterministic export, and verified recovery. It remains a structured JSON/form interface and makes no broad language-QA claim.

## Checks

- Branch: `exp/stage2-factual-memory`, based on frozen M-25.2 commit `9993cb91c84f3e39b0ba6816fa706264825eecb2`.
- Final branch HEAD is checked by `git rev-parse HEAD` in local and Karina exact-SHA logs.
- Ruff format/check: PASS.
- Pytest: 536 passed.
- M-25 deterministic acceptance: PASS, 452 checks in no-dataset regression mode.
- M-25.1 full fair acceptance: PASS; blind targets were not manually reopened.
- M-25.2 acceptance: PASS, 1,293 checks.
- M-26 acceptance: PASS, 18/18, accuracy 1.0000.
- Trusted CLI smoke: PASS.
- Trusted facts import loads torch: false.
- Karina 1k/10k/100k scale, backup, restore, export, integrity: PASS.

## Preflight

Assistive selections no longer infer `full_trace_equivalent=true` from missing structural-difference evidence. Only exact structural routes claim full identity. Final-state substitutions and assistive candidates remain false.

New learned retriever checkpoints bind SkillRegistry schema v3. M-25.1 v2 artifacts fail default loading with `ARCHIVAL_RESEARCH_ONLY` and `REBIND_OR_REEXPORT_REQUIRED`; historical research scripts use explicit archival opt-in and gain no routing authority.

## Architecture

- `FactMemory` is separate from RuleMemory and SkillRegistry.
- FactValue rejects float, NaN/infinity, bool-as-integer, malformed temporal/unit/entity values.
- Exact EntityRegistry returns ambiguity instead of fuzzy merge.
- PredicateDefinition drives object validation, temporal semantics, and conflicts.
- Content-addressed snapshots and evidence excerpt hashes are reverified before trust.
- Proposal stages cannot be skipped; changed dependencies invalidate approval.
- SQLite uses constrained rows, foreign keys, indexed time/routing fields, WAL, FULL sync, and `BEGIN IMMEDIATE`.
- No FactAnswerBundle field carries execution, dispatch, skill, rule, or write authority.

## Temporal and Conflict Results

Half-open valid intervals, adjacent boundaries, current, `VALID_AT`, `KNOWN_AT`, combined bitemporal queries, retroactive visibility, claim/source retraction, and supersession history pass.

Duplicate canonical claims merge evidence rather than values. Independent source families create corroboration; mirrored lineage does not. `SINGLE` overlap returns all competing claims. A retracted/unavailable source on one side does not silently promote the other side: the result remains `CONFLICT` with an affected-source warning.

## Provenance and Security

Span and RFC 6901 pointer verification, modified blobs, changed excerpts, malformed values, stale/tampered query and approval artifacts, reused query IDs, transaction rollback, supersession cycles, database/audit hash tampering, corrupt backup, no-torch import, and fact/rule separation fail closed.

Every trusted answer binds query, snapshot, claim, evidence, source, conflict, and renderer hashes. Old bundles remain immutable; replay reports `STALE_SNAPSHOT` after a memory write.

## Scale

Karina completed 100,000 claims in 211.18 seconds at 473.53 claims/s. Database size was 1.193 GB, source blobs 8.65 MB, and traced Python peak memory 143.6 MB. Exact subject+predicate p99 was 0.1932 ms; bitemporal p99 was 0.0182 ms. All measured plans used indexes. Backup took 2.324 s, restore 9.767 s, export 1.140 s, and full integrity 3.825 s.

See `docs/m26_scale_report.md` for all p50/p95/p99 values.

## Success Criteria

| Criterion | Result |
|---|---:|
| Trusted structured fact query | 1.0000 |
| valid_at / known_at / bitemporal | 1.0000 |
| Conflict detection | 1.0000 |
| Silent conflict winner | 0 |
| Provenance retention | 1.0000 |
| Duplicate evidence merge | 1.0000 |
| Supersession/retraction history | 1.0000 |
| Entity ambiguity silently resolved | 0 |
| Unapproved/model-authorized writes | 0 |
| Fact-triggered skill execution | 0 |
| Tampered source/evidence accepted | 0 |
| Backup/restore | 1.0000 |
| 100k benchmark | completed |
| Trusted import loads torch | 0 |

## Decision

Proceed to M-27 unified skill/fact/tool routing only while retaining typed authority boundaries: facts may answer factual queries, but cannot dispatch a skill; skill receipts cannot write facts; assistive language or learned routing cannot become factual authority.

The limitations in `docs/m26_limitations.md` remain release constraints, not deferred implementation details hidden from users.

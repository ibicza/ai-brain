# M-26 FactMemory Architecture

## Boundary

`ai_brain.stage2.facts` is a separate CPU-only package. It imports neither RuleMemory nor SkillRegistry and exposes no execute/dispatch callback.

```text
snapshot blob -> SourceRecord -> EvidenceRecord -> FactProposal
                                            -> validation/review/approval
                                            -> ClaimRecord/ConflictGroup
                                            -> FactQuery/FactAnswerBundle
```

## Authority

- SQLite is authoritative for records, relations, temporal events, receipts, and audit events.
- `blobs/sha256/<prefix>/<digest>` is authoritative for immutable source bytes.
- `FactApprovalEnvelope` is necessary but not sufficient: commit revalidates every bound hash and evidence excerpt.
- Model extraction remains `MODEL_PROPOSED`/`MODEL_EXTRACTION` until independently reviewed.

## Trusted and Assistive

Exact: typed values, schema validation, entity resolution, evidence addressing, hashes, interval comparisons, conflicts, approval, retrieval, rendering, backup, and replay.

Assistive only: future fuzzy entity candidates, document extraction, natural-language queries, ranking, and display scores.

## Concurrency

M-26 supports multiple readers and one writer. Writers use `BEGIN IMMEDIATE`, a 5-second busy timeout, foreign keys, WAL where available, and `synchronous=FULL`. It is not a distributed database.

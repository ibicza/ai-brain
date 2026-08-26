# M-26.1 Factual Integrity Report

## Result

**OUTCOME A - FACTUAL INTEGRITY HARDENED.**

The implementation is committed at
`6f0f1e76b852d078056b4a0e0aca6d54fbc77d0e` on
`exp/stage2-factual-integrity` and pushed to
`origin/exp/stage2-factual-integrity`. It was not merged into `gpt`.

## Delivered

- FactMemory schema/migration v2 and answer/rendering v2.
- Separate SUPPORTS and CONTRADICTS derivation, freshness, counts, hashes,
  citations, trust tiers, families, warnings, rendering, and audit.
- Typed HUMAN/TRUSTED_PROCESS/MODEL actor authority with fail-closed review,
  approval, retraction, supersession, and resolution guards.
- MODEL_INFERENCE independent-support policy bound into approval envelopes.
- One as-of transaction projection preventing future claim/source/evidence/
  conflict leakage and binding historical receipts.
- Append-only conflict-resolution events with source-retraction, claim-event,
  supersession, and reviewed manual-resolution policy.
- Enforced overlapping-interval policy and honest evidence-detail modes.
- Explicit current/record/as-of source and claim APIs.
- Non-destructive, hash-evidenced v1-to-v2 migration CLI/API.
- Deterministic 28-case acceptance and 10k/100k compatibility benchmark.

## Acceptance

| Check | Result |
|---|---:|
| SUPPORTS counted as support | 1.0000 |
| CONTRADICTS counted as support | 0 |
| False corroboration from contradiction | 0 |
| Hidden contradicting evidence | 0 |
| Retracted support masked by contradiction | 0 |
| Model self-approved claims | 0 |
| MODEL_INFERENCE-only trusted claims | 0 |
| Blank reviewer approvals | 0 |
| Future transaction event leakage | 0 |
| Historical known_at correctness | 1.0000 |
| Conflict as-of correctness | 1.0000 |
| Source-retraction silent winner | 0 |
| Claim-resolution history retained | 1.0000 |
| Overlap policy enforced | 1.0000 |
| Evidence references retained in compact mode | 1.0000 |
| v1-to-v2 migration | 1.0000 |
| FactMemory integrity | 1.0000 |
| Trusted import loads torch | 0 |
| Fact-triggered skill execution | 0 |

M-26 acceptance remained `18/18`. M-26.1 acceptance reached `28/28` on both
hosts. The dedicated security test file contains 29 results, including actor,
model-source, evidence/polarity tamper, temporal receipt, conflict-resolution,
schema-v1 direct-open, migration rollback, and old-answer rejection paths.

## Gates

Exact implementation SHA on both hosts:

| Gate | Local | Karina |
|---|---|---|
| Ruff format/check | PASS | PASS |
| Full pytest | 565 passed | 565 passed |
| M-25 | PASS, 453 checks | PASS, 453 checks |
| M-25.1 | PASS | PASS |
| M-25.2 | PASS, 1293 checks | PASS, 1293 checks |
| M-26 | PASS, 18/18 | PASS, 18/18 |
| M-26.1 | PASS, 28/28 | PASS, 28/28 |
| Migration/temporal/conflict/polarity/authority batteries | PASS | PASS |
| No-torch / facts CLI | PASS | PASS |
| Scale | 100/1000 smoke PASS | 10k/100k PASS |

Complete transcripts:

- `runs/m261_final_gate/local_exact_sha.log`:
  `a7efd2bd0acb8e8e4071ba59fdeacc08eb8de100f3b85201dc948d54917f8eb1`
- `runs/m261_final_gate/karina_exact_sha.log`:
  `717701ef54b8107145e8860a3724cc51ffa63bcb78c8d3919ebed3c349c06f57`

The 100k exact-query p99 was `0.3449 ms`; polarity/history/conflict-as-of p99
was at most `0.0137 ms`; all trusted exact query plans used indexes and reported
zero full scans. Full figures are in `docs/m261_scale_regression.md`.

## Source Control Safety

The feature commit descends from the required M-26 SHA
`7ee89dd6d439a5f3d50612520789c26e42746ce9`. Stage-1 tags, `gpt`, original M-26
reports/benchmarks, and M-25.1 blind artifacts were not modified. Final reports
and complete transcripts are added in a following evidence-only commit because a
commit cannot contain a transcript that names its own hash; the tested code SHA
remains explicit and unchanged.

M-26.1 therefore clears the factual-memory blockers and may proceed to M-27
unified routing while keeping conflict resolution reviewed and non-ranking-based.

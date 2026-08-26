# M-27 Authority-Aware Unified Router Report

## Decision

**Outcome A - unified router works.**

Exact fact, skill, and bounded local-tool routing is safe under the tested
catalog. Authority boundaries held, assistive routing remained review-only, and
both local and Karina exact-SHA gates passed at implementation commit
`8503d12392996e96159a61a76aa524f5a4070b47`.
## Implementation

M-27 adds FactMemory schema v3 and a separate trusted router package. FactMemory
now keeps logical `canonical_claim_hash` identity and full immutable
`claim_record_hash` integrity, supports non-destructive v2-to-v3 migration,
binds conflict-resolution evidence to claim sides, validates supersession
domains, and distinguishes current from explicitly historical queries.

The router provides immutable requests, decisions, receipts, clarifications,
dependency snapshots, one-route responses, exact structured routing, finite
controlled RU/EN grammars, a separate ToolRegistry, Decimal/date tools, explicit
skill/tool confirmations, stale-dependency rejection, checksummed SQLite
persistence, backup/restore, audit replay, and `ai-brain-router`.

## Exact-SHA Checks

| Check | Local Windows | Karina CPU |
|---|---:|---:|
| implementation SHA | `8503d123...` | `8503d123...` |
| ruff format/check | PASS | PASS |
| pytest | 585 PASS | 585 PASS |
| M-25 acceptance | PASS | PASS |
| M-25.1, no prior blind reopen | PASS | PASS |
| M-25.2 acceptance | PASS | PASS |
| M-26 acceptance | 18/18 | 18/18 |
| M-26.1 acceptance | 28/28 | 28/28 |
| v2-to-v3 migration focus | PASS | PASS |
| M-27 trusted acceptance | 1317 checks PASS | 1317 checks PASS |
| trusted import loads torch | false | false |
| CLI confirm/execute/verify | PASS | PASS |

The Karina gate initially called `FactMemory.backup`, while the existing backup
API is `FactMemory.database.backup`. The failed infrastructure command remains
in the log. The corrected API call then completed full 100k verify,
checksummed backup, restore, and a second full verify; both original and restored
stores reported `VALID`. No source change occurred.

## Preflight Integrity

- Claim payload tamper accepted: 0.
- Unrelated conflict evidence accepted: 0.
- Empty manual resolution accepted: 0.
- Cross-domain supersession accepted: 0.
- Default current query audited as historical: 0.
- v2-to-v3 migration: PASS, source bytes preserved.
- Corrupt source migration rollback: PASS.
- Router artifact payload tamper accepted: 0.
- Forged tool confirmation accepted: 0.
- Changed target or stale dependency accepted: 0.

## Trusted Routing

The final deterministic catalog reported:

| Metric | Result |
|---|---:|
| structured skills | 89/89 |
| controlled RU/EN skills | 356/356 |
| skill dispatches | 89/89 |
| controlled fact routes | 6/6 |
| Decimal tool executions | 50 |
| date tool executions | 30 |
| tool error rejections | 20 |
| unknown requests rejected | 100/100 |
| ambiguous requests blocked | 100/100 |
| composite requests blocked | 100/100 |
| wrong exact routes | 0 |
| wrong automatic executions | 0 |
| cross-authority writes | 0 |
| partial composite executions | 0 |
| persisted artifacts verified | 3540 |
| audit events verified | 3813 |

Fact answers carry no execution or write authority. Skill receipts carry no fact
approval. Tool results carry no fact-write, rule-installation, or skill
authority. One response can contain at most one authority-domain payload.

## Performance

All values are CPU milliseconds over 100 samples.

| Host / facts | Metric | p50 | p95 | p99 |
|---|---|---:|---:|---:|
| local / 10k | indexed SQL | 6.1759 | 7.0464 | 7.2070 |
| local / 10k | full FactMemory query | 47.0725 | 54.1979 | 58.3981 |
| local / 10k | unified fact response | 60.4936 | 65.7298 | 68.0918 |
| local / 100k | indexed SQL | 5.6455 | 43.0108 | 47.5460 |
| local / 100k | full FactMemory query | 88.8413 | 105.7058 | 112.1445 |
| local / 100k | unified fact response | 101.4574 | 120.5425 | 130.4304 |
| Karina / 100k | indexed SQL | 4.5737 | 5.4474 | 6.1234 |
| Karina / 100k | full FactMemory query | 101.1415 | 107.7894 | 109.4310 |
| Karina / 100k | unified fact response | 117.8784 | 121.9292 | 122.9018 |

Karina generated 100,000 schema-v3 claims at 424.65 claims/s. The final store
and restored backup each verified 200 blobs and 100,000 claim records.

## Assistive Research

The frozen M-27 dataset has 30k train, 4k validation, 4k calibration, 8k
development, and 8k blind rows with zero exact train/eval prompt intersections.
The deterministic character n-gram baseline reached:

- development top-1: 0.9905;
- development hard-cross-domain top-1: 0.8271;
- calibration top-1: 0.9893;
- blind top-1, one frozen opening: 0.9913;
- calibration unsupported, ambiguous, and composite recall: 1.0000;
- calibration macro one-vs-rest AUROC/AUPRC: 0.9689 / 0.9461;
- false exact authority: 0.

Wrapper-only accuracy was chance-level at 0.1663. Length/punctuation-only
accuracy remained 0.4959, so this dataset still has measurable surface signal.
The assistive model therefore orders manual-review candidates only. It cannot
create an exact route, answer facts, dispatch skills, execute tools, or write
memory. The selected baseline is deterministic and has no trainable model seed;
the frozen blind set was opened once and was not reused for tuning.

## Limitations

Exact routing is intentionally limited to finite controlled RU/EN grammars and
typed structured requests. Free text is assistive-only. Only deterministic local
read-only tools execute; network and side-effecting tools are unavailable.
There are no automatic fact writes from tools or skills, no autonomous conflict
winner, no hidden multi-step planning, no general natural-language QA, and no
distributed orchestration. One request produces one trusted route.

## Evidence

- `runs/m27_final_gate/local_exact_sha.log`
- `runs/m27_final_gate/karina_exact_sha.log`
- local and Karina trusted-acceptance JSON
- local 10k/100k and Karina 100k performance JSON
- Karina 100k corpus manifest
- frozen assistive manifest, recipe, blind-opening record, and report

The evidence commit changes no files under `src`, `tests`, `scripts`,
`pyproject.toml`, or `uv.lock` relative to implementation commit
`8503d12392996e96159a61a76aa524f5a4070b47`.

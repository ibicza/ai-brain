# M-27.1 Unified Router Hardening Report

## Outcome

**Outcome A - unified router hardened.** Dependency replay, bounded tools,
conflict-resolution integrity, migration, and the unified response lifecycle pass
on the exact implementation commit locally and on Karina.

## Source Control

- Branch: `exp/stage2-unified-router-hardening`
- Implementation commit H2: `0e93f5ba0f68da6022a80d9309f350359e455eaa`
- Implementation parent: `a85fe24a28f6c40025a4c228dfeb07f96759794b`
- Evidence commit: `M-27.1 exact-SHA evidence and reports`
- Stage-1 tags and `gpt` were not modified.

## Exact-SHA Checks

| Check | Local | Karina |
| --- | ---: | ---: |
| H2 SHA | exact | exact |
| Ruff format/check | PASS | PASS |
| Full pytest | 623 passed | 623 passed |
| M-25 acceptance | PASS | PASS |
| M-25.1 fair, no blind reopen | PASS | PASS |
| M-25.2 acceptance | PASS | PASS |
| M-26 / M-26.1 | PASS | PASS |
| M-27 trusted acceptance | 1317 checks | 1317 checks |
| All-skill dispatch | 89/89 | 89/89 |
| M-27.1 acceptance | 42 checks | 42 checks |
| Trusted import loads torch | false | false |

The M-27 regression retained 89 structured routes, 356 controlled routes, 50
Decimal executions, 30 date executions, zero wrong exact routes, zero partial
composite executions, and zero cross-authority writes on both hosts.

## Hardening Results

- Dependency replay mutations: 8/8 rejected with the expected granular status.
- Tool implementation-manifest mutations: 7/7 changed authority hashes.
- Decimal attack/resource cases: 14/14 typed rejections.
- Strict conflict-policy cases: 28/28 passed.
- RouterStore v1 to v2 migration: PASS; legacy incomplete responses are not current.
- FactMemory v3 to v4 migration: PASS; unsafe legacy resolutions require review.
- Tool lifecycle: PREPARED to COMPLETED and PREPARED to FAILED both PASS.
- Skill final response lifecycle and dependency binding: PASS.
- Router CLI route/verify/audit/backup/restore smoke: PASS.

## 100k Compatibility

Karina generated and verified a schema-v4 corpus with 100,000 claims, 105,000
evidence records, and 5,000 conflict groups/events. A non-destructive v3 fixture
was migrated to v4 with `source_unchanged=true`, 5,000 verified-v4 resolutions,
zero review-required events for this safe corpus, and a VALID target. Backup,
restore, and full verification of the restored 100k memory also passed.

## Performance

At 100 samples, local p95 latency was 3.18 ms for dependency snapshots, 23.58 ms
for full replay, 0.05 ms for Decimal validation, 229.31 ms for complete tool
responses, and 654.89 ms for complete skill responses. Karina p95 was 0.78 ms,
1.24 ms, 0.01 ms, 25.11 ms, and 116.62 ms respectively. Both benchmark stores
verified as VALID.

## Evidence

- `runs/m271_final_gate/local_exact_sha.log`
- `runs/m271_final_gate/karina_exact_sha.log`
- local and Karina M-25/M-25.1/M-25.2/M-27/M-27.1 acceptance JSON
- local and Karina performance JSON
- Karina 100k corpus and migration manifests

## Limitations

Exact language remains finite controlled RU/EN and assistive routing remains
review-only. There are only two bounded local read-only tools, no network or
side-effecting tools, no automatic fact writes or rule installation, no hidden
planner, and no autonomous conflict winner. Legacy incomplete receipts are not
trusted. Tool manifests attest an explicit dependency list rather than arbitrary
dynamic Python behavior. The system remains local and single-host at runtime.

## Recommendation

Proceed to M-28 with a first bounded educational domain built on the frozen exact
authority, replay, migration, and final-response contracts. Keep any broader
language or tool expansion outside trusted authority until it has an equivalent
validation battery.

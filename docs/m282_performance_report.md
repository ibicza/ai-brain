# M-28.2 Performance Report

The Windows CPU benchmark completed 10,000 mixed calculations with status `PASS`.

| Metric | Result |
|---|---:|
| Throughput | 144.49 calculations/s |
| Mixed calculation p50 / p95 / p99 | 6.78 / 13.61 / 15.90 ms |
| Peak Python memory | 8,681,154 bytes |
| Source-chain verification p50 / p95 / p99 | 249.00 / 299.81 / 299.81 ms |
| Derivation resolution p50 / p95 / p99 | 155.08 / 214.82 / 237.51 ms |
| Upstream-state resolution p50 / p95 / p99 | 15.39 / 28.55 / 36.05 ms |
| Knowledge snapshot p50 / p95 / p99 | 1667.66 / 1953.43 / 2005.37 ms |
| Proposal creation p50 / p95 / p99 | 174.28 / 197.64 / 1829.77 ms |
| Replay p50 / p95 / p99 | 274.40 / 323.01 / 342.92 ms |
| Pack load p50 / p95 / p99 | 287.85 / 294.70 / 294.70 ms |
| FactMemory verify | 869.48 ms |

Strict full-chain work is intentionally more expensive than a calculation. Internal caches are keyed by the current FactMemory snapshot hash, so ordinary current-state routes avoid rebuilding trusted snapshots while status changes invalidate cached trust.

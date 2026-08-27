# M-28.2 Performance Report

Both exact-H5 CPU benchmarks completed 10,000 mixed calculations with status `PASS`.

| Metric | Result |
|---|---:|
| Local Windows throughput | 160.15 calculations/s |
| Local mixed calculation p50 / p95 / p99 | 5.92 / 12.07 / 16.85 ms |
| Local peak Python memory | 8,681,702 bytes |
| Karina Linux throughput | 318.63 calculations/s |
| Karina mixed calculation p50 / p95 / p99 | 3.14 / 6.11 / 6.15 ms |
| Karina peak Python memory | 9,083,410 bytes |
| Local source-chain verification p50 / p95 / p99 | 209.90 / 243.45 / 243.45 ms |
| Local derivation resolution p50 / p95 / p99 | 147.58 / 169.59 / 203.64 ms |
| Local upstream-state resolution p50 / p95 / p99 | 14.49 / 16.00 / 18.04 ms |
| Local knowledge snapshot p50 / p95 / p99 | 1628.11 / 1773.35 / 1829.94 ms |
| Local proposal creation p50 / p95 / p99 | 175.15 / 206.74 / 1786.47 ms |
| Replay p50 / p95 / p99 | 274.40 / 323.01 / 342.92 ms |
| Pack load p50 / p95 / p99 | 287.85 / 294.70 / 294.70 ms |
| FactMemory verify | 869.48 ms |

The last three rows are from the initial Windows validation matrix; the exact-H5 JSON files retain the complete local and Karina matrices. Strict full-chain work is intentionally more expensive than a calculation. Internal caches are keyed by the current FactMemory snapshot hash, so ordinary current-state routes avoid rebuilding trusted snapshots while status changes invalidate cached trust.

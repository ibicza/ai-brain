# M-26.1 Scale Regression

Exact implementation SHA: `6f0f1e76b852d078056b4a0e0aca6d54fbc77d0e`.
Host: Karina, CPU-only trusted path. Existing M-26 schema-v1 corpora were
migrated; the 100k corpus was not regenerated through the manual workflow.

## Corpus And Migration

| Claims | V2 database | Migration | Manifest SHA-256 | CONTRADICTS added | Resolution events added |
|---:|---:|---:|---|---:|---:|
| 10,000 | 136,220,672 B | 59.974 s | `1680d151804ba97d0493f22cbd4ef7199b7d92e576c13a14cd1b42d40e11f989` | 100 | 50 |
| 100,000 | 1,342,599,168 B | 667.505 s | `f659703d56bc352b0811b0341fa625b451b407ab195d77ca65bd3547c34a40b6` | 1,000 | 500 |

Migration time includes source copying, schema-v1 SQLite/audit/row/blob
verification, schema upgrade, migration ledger and initial conflict-history
creation, full schema-v2 verification, manifest creation, publication, and final
verification. Both targets reported `VALID`; source tree hashes before and after
migration matched.

## Indexed Query Latency

All values are milliseconds over 500 samples.

| Claims | Query | p50 | p95 | p99 |
|---:|---|---:|---:|---:|
| 10,000 | exact subject/predicate | 0.0035 | 0.0069 | 0.0222 |
| 10,000 | bitemporal | 0.0033 | 0.0043 | 0.0119 |
| 10,000 | evidence polarity | 0.0033 | 0.0050 | 0.0075 |
| 10,000 | historical status | 0.0047 | 0.0072 | 0.0079 |
| 10,000 | conflict as-of | 0.0032 | 0.0046 | 0.0059 |
| 100,000 | exact subject/predicate | 0.0052 | 0.0247 | 0.3449 |
| 100,000 | bitemporal | 0.0047 | 0.0063 | 0.0278 |
| 100,000 | evidence polarity | 0.0048 | 0.0119 | 0.0137 |
| 100,000 | historical status | 0.0062 | 0.0079 | 0.0137 |
| 100,000 | conflict as-of | 0.0046 | 0.0060 | 0.0081 |

Every measured trusted exact query used its intended index. Both the original
query set and the new polarity/history set reported `full_scan_queries: []`.

## Recovery Operations

| Claims | Backup | Restore | Export | SQLite/audit/blob integrity |
|---:|---:|---:|---:|---:|
| 10,000 | 0.306 s | 0.821 s | 0.329 s | 0.266 s |
| 100,000 | 3.366 s | 12.181 s | 3.361 s | 4.248 s |

The restored copies passed integrity verification. The complete machine-readable
result is preserved as `runs/m261_final_gate/karina_scale_regression.json` with
SHA-256 `5e9242093d002559a5c12145ebf4204749a0b797a3a8d9ac25a505300e42847b`.

Conclusion: schema-v2 migration has a deliberate linear full-verification cost,
while normal exact, temporal, polarity, and conflict queries remain indexed and
viable at 100k.

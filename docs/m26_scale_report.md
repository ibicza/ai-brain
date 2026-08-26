# M-26 Scale Report

## Environment

- Host: Karina (`192.168.100.5`), Linux, CPU-only trusted path.
- GPU present but unused: NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB.
- Corpus seed: 26000 plus scale size.
- Samples per latency distribution: 500.
- SQLite: WAL, foreign keys ON, synchronous FULL, 5-second busy timeout.

## Corpus

The 100k corpus contains 1,000 fictional entities, 25 predicates, 200 immutable JSON source records, 100,000 accepted claims, 10,000 temporal updates, 5,000 intentional conflicts, 5,000 claim retractions, 5,000 duplicate independent-support attachments, 10 source retractions, RU/EN aliases, lineage duplicates, and all nine FactValue kinds.

Every accepted claim has all seven proposal stages, evidence, a hash-bound approval, a claim row, a claim/evidence transaction, and transaction state. Audit batches bind groups of 1,000 generated claims; full per-claim lifecycle replay is exercised by the acceptance pack.

## Scale

| Claims | DB bytes | Blob bytes | Generate s | Claims/s | Backup s | Restore s | Export s | Integrity s | Exact p99 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 14,077,952 | 83,564 | 2.05 | 488.03 | 0.067 | 0.133 | 0.020 | 0.043 | 0.0056 |
| 10,000 | 120,877,056 | 849,219 | 18.00 | 555.50 | 0.279 | 0.736 | 0.051 | 0.234 | 0.0211 |
| 100,000 | 1,192,554,496 | 8,645,785 | 211.18 | 473.53 | 2.324 | 9.767 | 1.140 | 3.825 | 0.1932 |

100k Python peak traced memory was 143,584,359 bytes.

## 100k Latency

| Query | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|
| exact subject + predicate | 0.0052 | 0.0206 | 0.1932 |
| valid_at | 0.0045 | 0.0074 | 0.0165 |
| valid_at + known_at | 0.0046 | 0.0061 | 0.0182 |
| unresolved conflict | 0.0031 | 0.0045 | 0.0052 |
| exact alias | 0.0032 | 0.0035 | 0.0053 |
| claim history | 0.0066 | 0.0088 | 0.0123 |

## Query Plans

All measured exact queries used an explicit or SQLite primary-key index. `full_scan_queries` was empty at 1k, 10k, and 100k. The conflict lookup required and now uses `idx_conflict_lookup(subject_entity_id, predicate_id, resolution_status)`.

## Integrity and Recovery

The 100k `PRAGMA integrity_check`, audit chain, row hashes, 200 unique blobs, and evidence pointers passed. Online backup, restore to a new directory, restored integrity verification, deterministic export, and cleanup passed at all sizes.

Performance is diagnostic, not a service-level guarantee. The result establishes that the exact SQLite design is viable at the requested 100k scale without pathological indexed-query scans.

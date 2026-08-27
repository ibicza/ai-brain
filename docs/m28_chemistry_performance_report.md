# M-28 Chemistry Performance Report

Local CPU run, 10,000 molar-mass calculations:

- throughput: 4,552.75 calculations/s
- formula parse: p50 0.0459 ms, p95 0.0571 ms, p99 0.0759 ms
- molar mass: p50 0.2131 ms, p95 0.2827 ms, p99 0.3798 ms
- controlled route: p50 73.0246 ms, p95 77.9825 ms, p99 258.3818 ms

The calculation path caches verified immutable snapshots by FactMemory snapshot and selected element set. Any FactMemory update changes the cache key and forces revalidation. Machine output is `runs/m28_chemistry_performance.json`.

Karina CPU exact-H3 run: 9,568.49 calculations/s; parser p50/p95/p99 0.0213/0.0386/0.0564 ms; molar mass 0.1058/0.1120/0.1355 ms; controlled route 38.0523/39.1245/142.6187 ms.

## Full Operation Matrix

Values are p50/p95/p99 milliseconds, measured on independently rebuilt packs.

| Operation | Local | Karina |
|---|---:|---:|
| domain pack load | 35.0863 / 48.6937 / 48.6937 | 13.7027 / 15.3099 / 15.3099 |
| element exact query | 31.6402 / 34.4097 / 36.9441 | 15.1587 / 15.7726 / 15.8411 |
| formula parse | 0.0586 / 0.1085 / 0.1410 | 0.0245 / 0.0429 / 0.0624 |
| formula composition | 0.3854 / 0.4806 / 0.6423 | 0.1214 / 0.1266 / 0.1488 |
| knowledge snapshot creation | 150.7077 / 160.1110 / 160.1110 | 73.6436 / 83.1394 / 83.1394 |
| molar mass | 0.2745 / 0.4021 / 0.4729 | 0.0990 / 0.1562 / 0.1644 |
| mass to moles | 0.5881 / 0.6340 / 0.6689 | 0.1735 / 0.1805 / 0.1922 |
| entities to moles | 0.0368 / 0.0664 / 0.0717 | 0.0173 / 0.0175 / 0.0211 |
| controlled route | 76.6433 / 91.5077 / 115.7292 | 38.2502 / 38.8787 / 40.0855 |
| complete confirmed response | 143.2399 / 150.4066 / 152.9767 | 77.3638 / 78.6214 / 80.7709 |
| result replay | 12.4872 / 14.1733 / 15.8468 | 6.5828 / 6.7356 / 7.1519 |
| FactMemory verify | 452.8664 / 482.9361 / 482.9361 | 227.1721 / 227.2871 / 227.2871 |
| backup and restore | 299.8580 / 299.8580 / 299.8580 | 90.0866 / 90.0866 / 90.0866 |

Raw matrices are in `runs/m28_final_gate/local_full_performance.json` and `karina_full_performance.json`.

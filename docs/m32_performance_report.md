# M-32 performance report

Precommit Windows CPU-only sample, three iterations, Python peak memory measured with `tracemalloc`:

| Operation | p50 ms | p95 ms | p99 ms | ops/s | peak bytes |
|---|---:|---:|---:|---:|---:|
| source load | 5.055 | 5.294 | 5.294 | 200.860 | 58,385 |
| segmentation | 71.203 | 72.823 | 72.823 | 13.956 | 236,437 |
| proposal generation | 30.245 | 31.431 | 31.431 | 32.725 | 101,746 |
| IR type checking | 20.633 | 20.729 | 20.729 | 48.794 | 46,966 |
| equation checking | 0.265 | 0.346 | 0.346 | 3,485.130 | 4,019 |
| conflict detection | 71.522 | 74.791 | 74.791 | 13.828 | 6,464 |
| review application | 0.310 | 0.422 | 0.422 | 2,919.140 | 3,172 |
| pack compilation | 251.577 | 253.111 | 253.111 | 3.989 | 1,239,437 |
| provider closure | 374.341 | 383.285 | 383.285 | 2.655 | 75,047 |
| installed currentness | 4,876.651 | 4,911.419 | 4,911.419 | 0.205 | 3,001,001 |
| held-out runtime solution | 0.270 | 0.322 | 0.322 | 3,541.913 | 3,648 |

Compilation and runtime query time are reported separately. Exact-H11 Windows and Karina samples supersede this preliminary table in evidence.

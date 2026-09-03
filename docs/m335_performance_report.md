# M-33.5 performance report

The values below are the p50/p95/p99 across the eight exact-I14 determinism
cases. Lookup and comparison operations were sampled 1,000 times per case.
Windows used four matrix workers and was co-scheduled with the exact-I14 full
development run; Karina used two matrix workers. These are gate observations,
not a controlled platform benchmark. Correctness and byte determinism take
priority over performance differences.

## Stage seconds

| Stage | Windows p50 | p95 | p99 | Karina p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| Canonical ingestion | 2.015533 | 3.233677 | 3.233677 | 0.105113 | 0.108387 | 0.108387 |
| Source indexing | 33.678506 | 33.932360 | 33.932360 | 13.076809 | 13.193728 | 13.193728 |
| Proposal construction | 2.168561 | 2.387701 | 2.387701 | 0.730976 | 0.735748 | 0.735748 |
| Evidence construction | 135.084808 | 140.317991 | 140.317991 | 27.430299 | 27.593048 | 27.593048 |
| Identity/conflict closure | 0.098417 | 0.107779 | 0.107779 | 0.037078 | 0.041905 | 0.041905 |
| Packability preflight | 0.672922 | 0.683388 | 0.683388 | 0.253798 | 0.259745 | 0.259745 |
| Candidate compilation | 154.281206 | 163.881488 | 163.881488 | 77.648241 | 77.821801 | 77.821801 |
| Candidate replay | 186.927706 | 194.197308 | 194.197308 | 62.685223 | 63.253198 | 63.253198 |

## Lookup, throughput and memory

| Measure | Windows p50 | p95 | p99 | Karina p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| Exact descriptor lookup, ns | 848,600 | 1,145,100 | 1,422,000 | 319,701 | 375,376 | 443,313 |
| Ambiguous alias lookup, ns | 1,472,000 | 2,282,200 | 2,789,500 | 472,849 | 509,959 | 557,208 |
| Component comparison, ns | 10,900 | 13,100 | 16,400 | 4,238 | 4,348 | 5,040 |
| Proposals/second | 13.822790 | 14.234795 | 14.234795 | 53.013481 | 53.246195 | 53.246195 |
| Peak Python memory, bytes | 1,371,275,264 | 1,371,832,320 | 1,371,832,320 | 1,403,174,912 | 1,404,465,152 | 1,404,465,152 |

The Windows and Karina matrix report hashes are respectively
`e75f5f2c877a633006b7ae01e9eb1d7fa39e2a1fb234049a54f0a2360d98017f`
and `4404b653bb71db211b1019c9b5450bf8780ab88332ce790a1ae4443f934b02c0`.

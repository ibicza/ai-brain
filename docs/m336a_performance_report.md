# M-33.6a performance report

Measurements were produced on clean detached worktrees at exact I16 `6cf0cda35b19a3efb97f3e4bcfc78f1b3fdec970`. Times are microseconds; throughput is operations per second. Correctness and fail-closed behavior take priority over these measurements.

| Operation | Windows p50 / p95 / p99 | Windows throughput | Karina p50 / p95 / p99 | Karina throughput |
|---|---:|---:|---:|---:|
| POM load/verification | 243 / 270 / 372 | 3,896.604938 | 141 / 153 / 235 | 6,952.571075 |
| checksum verification | 4 / 4 / 8 | 238,207.547170 | 2 / 2 / 4 | 480,952.380952 |
| license normalization | 9 / 9 / 13 | 109,071.274298 | 5 / 6 / 9 | 192,015.209125 |
| SCM license verification | 31 / 36 / 51 | 29,131.814249 | 17 / 20 / 26 | 54,126.473741 |
| source-tree correspondence | 2,929 / 3,115 / 3,127 | 339.272425 | 1,731 / 1,772 / 1,827 | 575.277896 |
| candidate qualification | 357 / 400 / 448 | 2,735.422365 | 222 / 228 / 232 | 4,481.320437 |
| denylist lookup | 10 / 18 / 60,908 | 506.395282 | 7 / 11 / 42,484 | 726.012319 |
| role-manifest serialization | 749 / 813 / 1,209 | 1,301.915492 | 442 / 465 / 946 | 2,195.318104 |
| disclosure-claim extraction | 531 / 565 / 660 | 1,865.189289 | 295 / 309 / 344 | 3,368.238511 |
| historical freeze verification | 6,016,793 / 6,036,945 / 6,036,945 | 0.166109 | 2,015,894 / 2,041,180 / 2,041,180 | 0.497360 |

Peak traced Python memory was 356,138,064 bytes on Windows and 356,094,488 bytes on Karina. Historical Git blob acquisition uses one `git cat-file --batch` process instead of hundreds of per-file subprocesses. The denylist p99 includes the first lazy load of the accumulated manifest; subsequent lookups are represented by the p50/p95 values.

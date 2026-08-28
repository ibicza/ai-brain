# M-29 Performance Report

Local CPU benchmark: 10,000 mixed trusted interactions, 43.568615 s, 229.523 interactions/s, peak Python memory 3,406,937 bytes.

| Operation | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: |
| Answer parsing | 0.1790 | 0.2645 | 0.3119 |
| Graph verification | 3.9400 | 7.1743 | 8.5267 |
| Concise render | 3.7885 | 9.8138 | 11.9275 |
| Full render | 4.2833 | 7.5708 | 9.0343 |
| Exercise generation | 2.4990 | 3.4284 | 4.3562 |
| Grading | 3.8058 | 9.5752 | 11.0755 |
| Hint generation | 3.6165 | 9.4904 | 11.4756 |
| Session transition | 0.8300 | 1.1858 | 1.4323 |

Machine-readable evidence is in `runs/m29/final/performance.json`.

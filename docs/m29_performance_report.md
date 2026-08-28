# M-29 Performance Report

Exact-H6 local CPU benchmark: 10,000 mixed trusted interactions, 42.691497 s,
234.239 interactions/s, peak Python memory 3,409,033 bytes.

Exact-H6 Karina CPU benchmark: 10,000 mixed trusted interactions, 25.419014 s,
393.406 interactions/s, peak Python memory 3,406,507 bytes.

| Operation | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: |
| Answer parsing | 0.1734 | 0.2334 | 0.3082 |
| Graph verification | 3.9082 | 6.9826 | 8.0642 |
| Concise render | 3.7949 | 9.5837 | 10.7474 |
| Full render | 4.2835 | 7.4572 | 8.3007 |
| Exercise generation | 2.4667 | 3.2578 | 3.5493 |
| Grading | 3.7073 | 9.6005 | 11.0100 |
| Hint generation | 3.5928 | 9.3156 | 10.4914 |
| Session transition | 0.8231 | 1.0924 | 1.3301 |

Machine-readable evidence is in `runs/m29/final/performance.json`.

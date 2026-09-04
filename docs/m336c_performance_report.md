# M-33.6c performance report

All measurements below were produced from clean, detached checkouts of exact I18
`4ec1642af9eb6509ec3cbccb998d8faa581c8755`. Windows and Karina used the same six
disclosed candidates and selected the same 120 Java sources with one selector
invocation and no rerun. Timings and memory are descriptive platform-local values;
the semantic artifacts are covered by the separate byte-comparison gate.

## End-to-end gates

| Measurement | Windows | Karina |
| --- | ---: | ---: |
| Quality targeted suite | 193 passed / 213.754 s | 193 passed / 66.050 s |
| Quality full suite | 1015 passed / 1595.474 s | 1015 passed / 340.727 s |
| Rehearsal preparation | 121.788 s | 56.994 s |
| Rehearsal production | 1201.856 s | 477.722 s |
| Rehearsal evaluation | 730.330 s | 288.819 s |
| Development-evidence build | 14.926 s | 4.070 s |

Both quality gates passed Ruff formatting, Ruff lint, the no-Torch/no-network
checks, exact-I18/clean/detached checks, and the full and targeted test suites.

## Typed performance measurements

Repeated operations report p50, p95, p99, throughput, and sample count. Values are
seconds unless stated otherwise.

| Operation | Platform | p50 | p95 | p99 | Throughput/s | Samples |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| SPDX snapshot load | Windows | 0.026087 | 0.038715 | 0.038715 | 35.238 | 10 |
| SPDX snapshot load | Karina | 0.007950 | 0.008036 | 0.008036 | 125.575 | 10 |
| License match | Windows | 0.000046 | 0.000072 | 0.000085 | 19,935.012 | 100 |
| License match | Karina | 0.000022 | 0.000026 | 0.000031 | 44,877.924 | 100 |
| Evidence fusion | Windows | 0.000249 | 0.000440 | 0.000440 | 3,360.403 | 6 |
| Evidence fusion | Karina | 0.000122 | 0.000149 | 0.000149 | 7,962.460 | 6 |
| Document-role classification | Windows | 0.000006 | 0.000011 | 0.000013 | 140,177.737 | 1000 |
| Document-role classification | Karina | 0.000003 | 0.000003 | 0.000003 | 394,633.599 | 1000 |
| Entry eligibility | Windows | 0.036315 | 0.124872 | 0.124872 | 15.120 | 6 |
| Entry eligibility | Karina | 0.017538 | 0.066820 | 0.066820 | 28.469 | 6 |
| Candidate qualification | Windows | 22.444640 | 25.569235 | 25.569235 | 0.062 | 6 |
| Candidate qualification | Karina | 12.508313 | 13.371378 | 13.371378 | 0.114 | 6 |
| Artifact-contract lookup | Windows | 0.000012 | 0.000026 | 0.000033 | 66,238.762 | 1000 |
| Artifact-contract lookup | Karina | 0.000006 | 0.000006 | 0.000009 | 171,972.339 | 1000 |
| Contract validation | Windows | 0.000126 | 0.000216 | 0.000292 | 7,580.696 | 100 |
| Contract validation | Karina | 0.000031 | 0.000035 | 0.000050 | 31,588.820 | 100 |
| Disclosure extraction | Windows | 0.000042 | 0.000080 | 0.000105 | 19,945.349 | 100 |
| Disclosure extraction | Karina | 0.000017 | 0.000019 | 0.000022 | 56,509.339 | 100 |

## Long-running measured operations

| Operation | Platform | Seconds | Throughput | Peak Python memory |
| --- | --- | ---: | ---: | ---: |
| Complete disclosed provenance | Windows | 120.693 | 13.953 entries/s | 67,005,911 bytes |
| Complete disclosed provenance | Karina | 56.747 | 29.675 entries/s | 67,004,783 bytes |
| Java production | Windows | 1197.844 | 2.938 targets/s | 1,445,298,176 bytes |
| Java production | Karina | 475.805 | 7.396 targets/s | 1,455,247,360 bytes |
| Independent evaluator | Windows | 44.843 | 79.879 targets/s | 80,944,547 bytes |
| Independent evaluator | Karina | 18.245 | 196.324 targets/s | 80,946,732 bytes |

For the single-sample long-running operations, the recorded p50/p95/p99 are all
the measured sample. Complete substage timings and the canonical numeric strings
are retained in
`runs/m336c_final_gate/<platform>/rehearsal/development/performance.json`.

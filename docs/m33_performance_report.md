# M-33 performance report

Windows runtime over 500 persistent saga turns:

- p50: 331,436,000 ns;
- p95: 386,053,300 ns;
- p99: 419,330,600 ns;
- throughput: 3.061724 turns/s;
- peak traced Python memory: 3,937,869 bytes.

The isolated source/golden run was similar: p50 329,547,700 ns, p95
371,001,700 ns, p99 399,782,000 ns, and 3.081021 turns/s.

The safe four-bundle ingestion/segmentation/proposal/evidence/pack orchestration
took approximately 14.4 seconds wall time on Windows. The frozen runner did not
emit per-stage timings after its initial conflict failure, so compilation-stage
p50/p95/p99 and per-operation query breakdowns are unavailable. They must not be
reconstructed or tuned after F12. Karina measurements are recorded in E12.

Karina runtime over the same 500 semantic keys and installed H12 packs:

- p50: 120,009,663 ns;
- p95: 140,908,542 ns;
- p99: 144,001,475 ns;
- throughput: 8.215896 turns/s;
- peak traced Python memory: 3,936,480 bytes.

Karina's frozen ordinary compiler reproduced the Windows semantic-identity
failure before completing a four-bundle build. Cross-platform compilation-stage
percentiles and successful rebuilt-pack byte comparison are therefore
unavailable and are recorded as a failed gate, not silently omitted.

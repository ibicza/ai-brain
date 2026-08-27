# M-28.1 Performance Report

Exact-H4 Windows CPU benchmark, 10,000 mixed calculations:

- throughput: 201.78 calculations/s;
- p50: 4.676 ms;
- p95: 9.572 ms;
- p99: 18.063 ms;
- peak traced Python memory: 917,688 bytes.

Exact-H4 Karina Linux CPU benchmark:

- throughput: 503.04 calculations/s;
- p50: 1.990 ms;
- p95: 3.812 ms;
- p99: 3.862 ms;
- peak traced Python memory: 912,402 bytes.

The mix covers conventional/envelope molar mass, mass/amount, formula entities,
total atoms, and significant rendering. The operation matrix additionally covers
source verification, pack load, resolution, atomic-weight answers, parsing,
snapshot construction, controlled routing, confirmed response, replay,
FactMemory verification, backup, and restore.

Current-state snapshot creation and atomic-weight answers intentionally pay the
cost of querying and verifying provenance. Raw local and Karina operation
matrices are under `runs/m281_final_gate/`.

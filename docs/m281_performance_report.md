# M-28.1 Performance Report

Pre-commit Windows CPU benchmark, 10,000 mixed calculations:

- throughput: 242.70 calculations/s;
- p50: 3.971 ms;
- p95: 7.807 ms;
- p99: 9.918 ms;
- peak traced Python memory: 917,688 bytes.

The mix covers conventional/envelope molar mass, mass/amount, formula entities,
total atoms, and significant rendering. The operation matrix additionally covers
source verification, pack load, resolution, atomic-weight answers, parsing,
snapshot construction, controlled routing, confirmed response, replay,
FactMemory verification, backup, and restore.

Current-state snapshot creation and atomic-weight answers intentionally pay the
cost of querying and verifying provenance. Final exact-H4 local and Karina CPU
measurements are evidence artifacts, not implementation inputs.

# M-28 Chemistry Performance Report

Local CPU run, 10,000 molar-mass calculations:

- throughput: 4,552.75 calculations/s
- formula parse: p50 0.0459 ms, p95 0.0571 ms, p99 0.0759 ms
- molar mass: p50 0.2131 ms, p95 0.2827 ms, p99 0.3798 ms
- controlled route: p50 73.0246 ms, p95 77.9825 ms, p99 258.3818 ms

The calculation path caches verified immutable snapshots by FactMemory snapshot and selected element set. Any FactMemory update changes the cache key and forces revalidation. Machine output is `runs/m28_chemistry_performance.json`.

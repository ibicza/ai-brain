# M-27 Performance Report

Performance is measured as three separate distributions. SQL lookup is never
presented as total query latency. Each local Windows CPU result below uses 100
samples and milliseconds.

| facts | metric | p50 | p95 | p99 |
|---:|---|---:|---:|---:|
| 10,000 | indexed SQL lookup | 6.1759 | 7.0464 | 7.2070 |
| 10,000 | end-to-end `FactMemory.query()` | 47.0725 | 54.1979 | 58.3981 |
| 10,000 | unified router fact response | 60.4936 | 65.7298 | 68.0918 |
| 100,000 | indexed SQL lookup | 5.6455 | 43.0108 | 47.5460 |
| 100,000 | end-to-end `FactMemory.query()` | 88.8413 | 105.7058 | 112.1445 |
| 100,000 | unified router fact response | 101.4574 | 120.5425 | 130.4304 |

The benchmark entry point is `scripts/m27_performance.py`. Exact-SHA Karina CPU
measurements are retained separately in final gate evidence. Trusted routing and
orchestration remain CPU-only.

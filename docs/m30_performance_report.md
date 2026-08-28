# M-30 performance report

`scripts/m30_benchmark.py` measures 10,000 mixed controlled turn parses, 10,000
state transitions, 10,000 pending preparations and confirmations, 10,000
progress projections and recommendations, plus persisted progress append,
exercise presentation, answer submission, grading, hint, solution, replay,
structural backup and authority verification. Every stage reports
p50/p95/p99 latency, throughput and peak Python memory. Slow mutating educational
stages use an explicit bounded sample count; normal turns use bounded dependency
closure and never run a full-store verification.

# M-31 performance report

Local CPU baseline (10,000 operations each) is read from
`runs/m31/local_acceptance.json`. The gate records p50, p95, p99, throughput, and
peak Python memory for IR validation, capability lookup, and runtime family
lookup. Candidate indexes are constructed once from the verified immutable
catalog; no full registry verification occurs on the hot path.

The final pre-H10 baseline has p50/p95/p99 of 0.1282/0.2314/0.2885 ms for IR
validation, 0.0066/0.0112/0.0144 ms for capability lookup, and
0.0034/0.0059/0.0075 ms for exercise-family resolution. The expanded gate also
measures pack and registry load, approval verification, installation, installed
lookup, concept-graph lookup, catalog candidate resolution, recommendation,
runtime currentness, and a complete chemistry conversation path. The latter has
p50/p95/p99 of 1153.0925/1197.3061/1203.9654 ms over 25 isolated conversations.

Karina exact-H10 CPU metrics are recorded verbatim in the evidence-only run data;
local values are a CPU baseline, not a cross-machine performance promise.

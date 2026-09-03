# M-33.5 performance report

The development runner measures canonical ingestion, source indexing,
segmentation, proposal construction, field-evidence construction, identity
conflict closure, packability preflight, the complete production closure,
candidate compilation, isolated registry installation, standalone replay and
peak Python process memory. It also samples exact-descriptor lookup, ambiguous
alias lookup and component-manifest comparison 1,000 times per matrix case.
Exact Windows/Karina p50, p95, p99 and throughput measurements are E14 evidence;
correctness and byte determinism take priority over small regressions.

# Windows timeout forensics

Node: `tests/test_m29_educational_layer.py::test_chemistry_cli_builds_clean_pack_from_explicit_sources`. H15 evidence was 903 passed plus this 120-second timeout; an isolated retry passed in 108.85 s.

An instrumented clean build measured 107.6669 s total: import/startup 0.6694 s, source copy 0.0242 s, durable SQLite fact construction 105.4987 s, manifest build/write 0.7067 s, final open/verify 0.7498 s; peak traced Python memory was 15,607,278 bytes. A separate pytest invocation completed in 79.90 s. The process tree is pytest Python -> one chemistry CLI Python; completion left no child process.

The root cause is the Windows-tail latency of hundreds of intentionally durable FactMemory proposal/approval/commit transitions (`synchronous=FULL`), amplified by full-suite filesystem/antivirus contention. It is not source copy, CLI import, a dead wait, or accidental repeated source derivation. The fix preserves all assertions and durability semantics and replaces the generic 120 s cap with a measured clean-build-only 300 s ceiling. Final I16 requires three consecutive passes and one authoritative full-suite run, not an isolated retry substitution.

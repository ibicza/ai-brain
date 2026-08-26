# M-26 Provenance-Aware Bitemporal Factual Memory Report

Outcome A: the factual-memory core works.

- Local pytest: 536 passed.
- M-25, M-25.1, M-25.2 trusted regressions: PASS.
- M-26 acceptance: 18/18, 1.0000.
- Karina scale: 1k, 10k, 100k complete.
- 100k exact p99: 0.1932 ms; bitemporal p99: 0.0182 ms.
- 100k backup/restore/export/integrity: PASS.
- No full scans in measured indexed queries.
- Trusted fact import loads torch: 0.
- Silent conflict winners, unapproved writes, model-authorized writes, and fact-triggered skill execution: 0.

The complete architecture, security, temporal, provenance, scale, and limitations evidence is in `docs/m26_provenance_aware_factual_memory_report.md` and the other `docs/m26_*` documents.

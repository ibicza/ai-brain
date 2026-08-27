# M-28.2 Chemistry Provenance Closure Run Report

Outcome: **B — chain closed with reviewed manual mappings**.

- Domain/schema: `1.2.0` / `3`
- Source chain/policy: `3.0` / `3.0`
- Categories: 4 official, 1 local policy, 4 derived
- Derivations: 1 deterministic, 2 reviewed manual, 1 policy transformation
- Source-chain hash: `bb23631f47d927d4279d3744b735beec2f246e44c13b223f78d7f526a8dd898f`
- Domain reproducible hash: `0e2fd50177635d1b60c3504bb25fcaccee11a0c158d2b02a59226c4ad0d0011f`
- Acceptance: 2662 cases, PASS
- Source attacks: 101/101 rejected
- Upstream transitions: 30/30 blocked
- Field evidence: 534/534
- H5: `05ab4b994e28e92c4457cbea560c219588ccb541`
- Local exact-H5 pytest: 701 passed
- Karina exact-H5 pytest: 701 passed
- Windows 10k benchmark: PASS, 160.15 calculations/s, 5.92/12.07/16.85 ms p50/p95/p99
- Karina 10k benchmark: PASS, 318.63 calculations/s, 3.14/6.11/6.15 ms p50/p95/p99
- Official reacquisition: 4/4 exact expected hashes
- Windows/Linux source chain: 16/16 files byte-identical
- Trusted runtime: no torch, no network
- Policy scope: no moral/moderation/refusal policies added

IUPAC and BIPM are reviewed manual mappings. CIAAW is deterministic HTML-table extraction. E5 is the evidence-only commit containing this report and the exact-H5 logs; its forbidden-path diff is empty.

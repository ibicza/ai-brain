# M-26.1 Factual Integrity Report

Outcome: **A - factual integrity hardened**.

Tested implementation SHA:
`6f0f1e76b852d078056b4a0e0aca6d54fbc77d0e`.

## Exact Results

- Local and Karina ruff format/check: PASS.
- Local and Karina full suite: `565 passed`.
- M-25: PASS, 453 checks on both hosts.
- M-25.1: PASS on both hosts without modifying committed blind artifacts.
- M-25.2: PASS, 1293 checks on both hosts.
- M-26 acceptance: `18/18` on both hosts.
- M-26.1 acceptance: `28/28` on both hosts.
- Migration, temporal, conflict, polarity, model-authority, no-torch, and CLI
  batteries: PASS on both hosts.
- Karina existing-corpus regression: 10k/100k PASS, integrity VALID, no trusted
  exact query full scans.

100k p99 latency was `0.3449 ms` for exact subject/predicate, `0.0278 ms` for
bitemporal, `0.0137 ms` for polarity aggregation, `0.0137 ms` for historical
status, and `0.0081 ms` for conflict as-of. Migration with complete pre/post
verification took `667.505 s`; backup/restore took `3.366/12.181 s`.

## Evidence

- `runs/m261_final_gate/local_exact_sha.log` SHA-256:
  `a7efd2bd0acb8e8e4071ba59fdeacc08eb8de100f3b85201dc948d54917f8eb1`
- `runs/m261_final_gate/karina_exact_sha.log` SHA-256:
  `717701ef54b8107145e8860a3724cc51ffa63bcb78c8d3919ebed3c349c06f57`
- `runs/m261_final_gate/karina_scale_regression.json` SHA-256:
  `5e9242093d002559a5c12145ebf4204749a0b797a3a8d9ac25a505300e42847b`

The branch is `exp/stage2-factual-integrity`, pushed to origin and not merged
into `gpt`. Stage-1 tags, M-25.1 blind artifacts, and original M-26 reports remain
unchanged.

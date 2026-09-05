# M-33.6e disclosed full-path qualification

The disclosed rehearsal consumes only the existing M-33.6d external vault,
current thirty-entry registry, frozen authority statement, candidate pool, and
committed public receipts. It performs no network acquisition and never invokes
the historical M-33.6d selector or sentinel.

`m336e_run_disclosed_preflight.py` physically verifies the vault, re-runs all 24
candidate correspondence/legal/SPDX decisions, reissues and verifies authority
receipts, requires byte-equality with the historical qualification report, builds
source bindings, runs production-index-backed census and feasibility, then uses a
fresh disclosed-only ledger for exactly one selector invocation. The selected raw
snapshot and ledger remain external to Git.

Production, compilation, replay, cross-platform comparison, independent SPDX and
semantic evaluation, installation/runtime, public contract validation, leak scan,
and readiness must all pass from exact R20 before Q20 may be created. Q20 is
evidence-only; a single failed criterion stops the chain before F20.

The evaluator consumes the disclosed `candidates` report only through the same
contract-v2 qualification adapter used by the H20 public producer. The adapter
emits typed per-candidate authority and publication decisions, validates them
against `h20/qualification_summary.json`, and only then constructs evaluator
authority.

# M-33 generic persistent tutor

The generic provider loads only an installed content-addressed pack and its
current provider/capability closure. Presentations, grades, hints, explanations,
and command responses are written to append-only checksummed SQLite ledgers.
Conversation and learner progress use the established persistent stores and
public DTO boundary.

Equation exercise keys are calculated from the installed `RuleContent` through
the typed affine solver; no fixed answer is embedded. Explanations bind the
actual record hash, source-binding hashes, capability receipt hashes, pack hash,
and installation evaluation hash. Query providers cover bounded record,
taxonomy, temporal, API-contract, and equation operations. Unknown knowledge or
missing authority returns an explicit epistemic/capability status.

Runtime currentness verifies the installed pack bytes, semantic hash, provider
and capability registries, resolution receipts, and executable pack evaluation.
Replay, backup/restore, and restart use persisted state. Final isolation removes
source snapshots and goldens from the runtime path after installation; the
provider has no API that reads either.

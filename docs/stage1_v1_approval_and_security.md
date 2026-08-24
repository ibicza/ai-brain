# Stage-1 v1 Approval And Security

Installation requires an explicit `APPROVE` decision with non-empty identity and identity type `USER` or `TRUSTED_SUPERVISOR`.

The `ApprovalEnvelope` binds:

- proposal ID and content hash;
- final specification hash;
- candidate hash;
- verification-evidence hash;
- approver identity, type, timestamp, and Stage-1 version.

An edit increments the proposal revision and invalidates existing verification and approval. Installation checks every binding, parses the candidate again, reruns large property verification, and only then persists. Rejection, stale hashes, missing evidence, wrong status, duplicate semantics, deprecated rules, and malformed state fail closed.

Audit records are JSONL events linked by `previous_hash` and `event_hash`. Replay rejects missing, reordered, or modified events.

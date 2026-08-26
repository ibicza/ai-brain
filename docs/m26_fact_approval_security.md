# M-26 Fact Approval Security

Proposal stages are ordered: RECEIVED, PARSED, EVIDENCE_ATTACHED, VALIDATED, REVIEWED, APPROVED, COMMITTED. Terminal failures cannot re-enter the workflow.

Approval binds proposal, entity definition, predicate definition, typed value, qualifiers, valid interval, source records, evidence records, reviewer identity/type, decision, policy version, schema version, and timestamp.

Commit reloads and verifies those dependencies. Edited/stale artifacts fail. `MODEL_EXTRACTION` cannot self-approve. `MARK_CONTESTED` requires explicit contested approval. Fact approvals confer no RuleMemory installation authority.

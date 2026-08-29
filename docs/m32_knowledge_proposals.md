# Knowledge proposals

`KnowledgeProposal` is immutable and separate from installed knowledge. It binds source bundle and segment IDs, typed content, epistemic character, dependencies, applicability, capabilities, extraction method, ambiguity fields, compiler/schema versions, status, and proposal hash.

Statuses are `PROPOSED`, `VERIFIED`, `REVIEW_REQUIRED`, `CONFLICT`, `NEEDS_NEW_CAPABILITY`, `REJECTED`, and `APPROVED`. Only deterministic structured extraction without unresolved fields can become automatically `VERIFIED`; verification is not approval or installation.

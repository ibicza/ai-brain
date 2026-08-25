# M-24.1 Verified Review Workflow

The production state sequence is:

`REVIEWED -> VERIFIED -> VERIFIED_REVIEWED -> APPROVED -> INSTALLED -> EXECUTED`

`review-verification` renders the actual candidate and all verifier results after acquisition. The artifact hash covers the original input, specification/effect summary, register behavior, termination, phase order, compiler, canonical DSL, candidate/evidence hashes, version, warnings, and timestamp.

Approval validates the artifact against both current proposal and candidate and binds `verified_review_hash`. Any edit, changed candidate/evidence, altered review, stale version, blank identity, wrong identity type, or non-`APPROVE` decision fails closed. Installation emits a receipt; execution validates that receipt against proposal, requested rule ID, RuleMemory semantic hash, and specification hash.

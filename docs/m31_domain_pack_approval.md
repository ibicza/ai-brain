# Domain Pack approval

Installation requires every stage: strict load, IR validation, concept graph
validation, provenance reference validation, capability resolution, evaluation
manifest, human/trusted-process review, exact approval, installation, activation.
The approval envelope binds all hashes and receipts plus reviewer identity/type,
decision, policy, timestamp, schema, and approval hash. A MODEL or blank reviewer
cannot approve. Decisions are APPROVE, REJECT, REVIEW_REQUIRED, and
NEEDS_NEW_CAPABILITY; no stage is silently skipped.

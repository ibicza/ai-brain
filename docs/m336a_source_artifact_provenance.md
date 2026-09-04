# Source artifact provenance

`source_artifact_provenance.py` separates coordinate identity, downloaded digest evidence, repository/network metadata, license claims and texts, immutable SCM revision, source correspondence, qualification, and audit events. `semantic_identity_hash` excludes acquisition time, host, run ID, and network audit aggregation; `envelope_hash` binds both semantic identity and audit event.

The generic core contains no Java subject semantics. It defines the six evidence modes, conservative provenance states, five correspondence states, required/optional candidates, and seven qualification statuses. POM-only evidence is review-required, conflicts block, and external-license eligibility requires immutable revision plus complete correspondence.

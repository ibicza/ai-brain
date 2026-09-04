# M-33.6 applicability closure

Compilation no longer drops a missing applicability alias. Each applicability entry
must resolve to one exact KnowledgeRecord reference, be an explicitly validated
`inline-condition:<sha256>` typed condition, become `REVIEW_REQUIRED`, or fail
compilation. Empty applicability remains valid.

Regression tests cover missing, ambiguous, conflicting, exact, empty, and inline
typed applicability. The generic compiler has no membership-test branch that can
silently skip an unresolved reference.

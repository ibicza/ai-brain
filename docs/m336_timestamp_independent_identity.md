# M-33.6 timestamp-independent identity

Java compilation uses the semantic epoch `1970-01-01T00:00:00Z` in semantic
KnowledgeRecords, pack manifests, and replay bundles. Acquisition and compilation
event time is recorded separately by `JavaCompilationAuditReceipt`.

Changing `imported_at`, wall clock, timezone, or locale cannot change the production
semantic output, packability report, candidate pack semantic tree, replay artifact,
or installed knowledge content. An audit receipt may change only its explicit audit
fields and audit hash; its semantic compilation hash remains stable.

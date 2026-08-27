# Derived Source Binding

`SourceDerivationRecordV2` binds each derived source to its identity, media type, relative path, exact file SHA-256, canonical-content hash, expected FactMemory snapshot/record hashes, upstream references, extraction implementation, policy, method, and field evidence.

`resolve_source_derivation()` rejects missing, duplicate, borrowed, or swapped derivations; changed source IDs; changed bytes or canonical JSON; stale source records; changed upstream IDs, families, hashes, or records; invalid method policy; invalid approval; and altered field mappings.

Derived JSON is imported as exact bytes. Consequently the FactMemory `SourceRecord.snapshot_hash` equals the derived file SHA-256, while the canonical hash independently protects semantic JSON content.

The acceptance matrix exercised 101 mutations. All 101 were rejected: 80 as source mismatches and 21 as content mismatches. No fallback source and no automatic fact write occurred.

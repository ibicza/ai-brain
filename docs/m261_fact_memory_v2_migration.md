# FactMemory Schema-v1 To Schema-v2 Migration

M-26.1 sets both `FACT_MEMORY_SCHEMA_VERSION` and
`FACT_MEMORY_MIGRATION_VERSION` to `2`. `FactMemory.open` rejects schema-v1
directly; migration is explicit:

```powershell
uv run ai-brain-facts --root <new-v2-root> migrate --source-root <v1-root>
```

## Safety Sequence

1. Reject identical, nested, missing, or nonempty target paths.
2. Hash the complete source tree.
3. Copy v1 to a private staging snapshot.
4. Verify metadata/application ID, SQLite integrity, every immutable row hash,
   audit chain, evidence relation, and every referenced source blob.
5. Copy the verified snapshot to a separate v2 staging target.
6. Add v2 actor columns, polarity indexes, migration ledger, and append-only
   conflict resolution history.
7. Preserve legacy hashes and bind exact interpreted-v2 hashes in
   `migration_record_hashes` where v1 did not contain a v2 field.
8. Append the migration audit event and run full schema-v2 `FactMemory.verify()`.
9. Emit a manifest with source/target tree, database, snapshot, record, polarity,
   blob, migration-ledger, and manifest SHA-256 evidence.
10. Publish the target only after verification, then verify it again.

Any exception removes staging and an empty target. The source tree is hashed again
and must match byte-for-byte. A corrupt blob, audit event, immutable payload, row
hash, or partial/incorrect schema therefore fails closed without overwriting v1.

Historical v1 hashes remain authoritative. For fields introduced in v2, the
migration ledger is the only accepted bridge between the exact source hash and
the deterministic v2 interpretation; arbitrary hash differences are rejected.

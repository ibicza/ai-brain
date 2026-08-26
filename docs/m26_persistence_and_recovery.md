# M-26 Persistence and Recovery

SQLite settings: foreign keys ON, WAL where supported, synchronous FULL, application ID `AIBF`, 5-second busy timeout, and single-writer `BEGIN IMMEDIATE`.

Integrity layers:

- SQLite `integrity_check` and foreign keys;
- schema/migration/application versions;
- per-record canonical hashes;
- append-only audit hash chain;
- source and excerpt SHA-256;
- logical memory snapshot hash;
- deterministic JSONL export hashes.

Online backup uses SQLite's backup API and a blob manifest. Restore only targets a new empty directory, verifies database, audit, snapshot, and every blob, then records recovery provenance. It never overwrites a corrupt primary; operators preserve it and restore beside it.

The canonical export contains entities, predicates, sources, evidence, claims, relations, and a manifest. Physical SQLite bytes are not used as the only logical integrity identity because WAL/checkpoint state can change them.

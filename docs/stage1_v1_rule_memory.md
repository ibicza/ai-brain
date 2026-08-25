# Stage-1 v1 RuleMemory

Schema version 1 stores canonical programs, concrete semantic hashes, verification status, complete specification, evidence, versions, deprecation state, and provenance. `content_sha256` is mandatory. Normal load rejects a missing, malformed, or mismatched checksum, unknown fields, malformed records/specifications/DSL, duplicate IDs, duplicate active semantics, and status/evidence mismatch.

Save renders and validates the future payload before replacement. It writes a same-directory temporary file, flushes and `fsync`s it, atomically replaces the target, and attempts parent-directory `fsync`. Windows filesystems may not support directory `fsync`; that failure is an explicit documented fallback. An existing primary must validate before it becomes a validated `.bak`.

`load_with_backup` is fail-closed. It uses only a fully valid backup and exposes `recovery_source` as `primary` or `backup:<path>`; if both copies fail it reports both failures.

Checksum-less schema-v1 files are legacy inputs, never normal production inputs. They require explicit migration, strict legacy parsing, active-rule property re-verification, a checksummed destination, a preserved legacy backup, and migration evidence.

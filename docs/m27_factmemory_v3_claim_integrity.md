# M-27 FactMemory v3 Claim Integrity

FactMemory schema and migration versions are 3. `canonical_claim_hash` remains the logical duplicate identity over subject, predicate, value, qualifiers, and valid interval. New `claim_record_hash` binds the complete immutable persisted claim record, including claim ID, recorded time, base status, proposal/approval hashes, and schema version.

`FactMemory.verify()` checks both hashes independently and detects payload-only mutation. Schema v2 is rejected by ordinary open. `migrate_v2_to_v3` verifies v2 first, preserves the source tree byte-for-byte, builds in staging, adds and verifies every record hash, emits a hash-bound manifest, and publishes only after full v3 verification.

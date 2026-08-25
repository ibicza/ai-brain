# M-25 Skill Registry Schema

## SkillRecord

Each of the 89 active semantic rules maps to one `SkillRecord`. Records bind `skill_id`, `rule_id`, semantic hash, specification hash, installed receipt hash, rule version, active/deprecated state, bilingual names/aliases/examples, effect and state schemas, pre/postconditions, family, provenance, timestamps, and schema version.

Skill IDs are deterministic metadata derived from semantic hashes. They are labels only and never occur in model-visible query or skill-encoder text.

## Manifest

`SkillRegistryManifest` binds registry version/hash, complete RuleMemory hash, Stage-1 version, Stage-2 schema, skill/active counts, family counts, alias/description counts, and timestamps. Registry hash covers the manifest with a zeroed hash field plus all records in sorted order.

## Integrity Rules

Validation rejects:

- missing/orphan, inactive, deprecated, or unverified rules;
- changed semantic/specification hash or rule version;
- changed/stale installed receipt provenance;
- duplicate skill IDs or active semantic hashes;
- malformed bilingual metadata;
- incompatible Stage-1 or changed RuleMemory fingerprint;
- record, active, family, or registry-hash count mismatch.

Metadata updates are copy-on-write: they return a new registry version and hash. The record mapping is read-only.

## Persistence

The root key set is exact: `schema_version`, `manifest`, `records`, and mandatory `content_sha256`. Root, manifest, and record keys/types are strict, including bool-versus-int checks, SHA-256 syntax, timezone-bearing timestamps, array/object types, and schema versions.

Writes use a same-directory temporary file, stream and directory fsync, atomic replace, validated backup, and post-write validation. A corrupt primary may be read from backup but cannot be saved until explicit recovery preserves the corrupt bytes and restores the validated backup. Checksum-less and unknown-field files are rejected.

## Routing Artifacts

`SkillQuery` gives every attempt a unique query ID while identical input retains the same input hash. `SkillSearchResult` binds query, registry, RuleMemory, retrieval mode, ranked evidence, ambiguity/novelty state, next action, and result hash. `SkillSelectionReceipt` additionally binds candidate-list hash and confirmation. `SkillDispatchReceipt` binds selection, skill/rule/receipt hashes, initial state, limits, Stage-1 execution hash, policy, and final dispatch hash.

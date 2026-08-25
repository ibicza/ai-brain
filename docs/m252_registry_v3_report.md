# M-25.2 SkillRegistry V3 Report

## Schema Change

- `STAGE2_SCHEMA_VERSION = 3`.
- `SKILL_REGISTRY_SCHEMA_VERSION = 3`.
- Persisted `semantic_effect_hash` is renamed to
  `final_state_effect_hash`.
- Persisted class count is renamed to
  `final_state_effect_class_count`.
- `full_execution_equivalence_class_count` and
  `trace_distinct_class_count` are mandatory manifest fields.

The v3 manifest recomputes and validates every count independently:

- 89 structural skills;
- 57 final-state effect classes;
- 89 full-execution identity classes;
- 16 trace-distinct classes;
- 24 order-sensitive and 33 order-insensitive classes;
- class-size distribution `41 x 1`, `12 x 2`, `4 x 6`.

## Compatibility Policy

A persisted v2 registry is not silently interpreted under v3 semantics. Loading
it fails with an explicit instruction to rebuild from verified RuleMemory.

SkillRegistry is derived metadata, so the safe upgrade path is:

1. load and verify the frozen RuleMemory;
2. call `rebuild_from_rule_memory()` with installed receipts;
3. validate the new registry against the same RuleMemory;
4. persist a checksummed v3 registry.

The M-25 and M-25.1 v1/v2 artifacts remain unmodified historical evidence.
Compatibility source aliases exist only for old Python imports and are not
persisted in v3 JSON.

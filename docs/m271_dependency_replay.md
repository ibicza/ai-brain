# M-27.1 Dependency Replay

Every trusted route and response binds an immutable `DependencySnapshot` and its
`dependency_snapshot_hash`. The snapshot covers FactMemory and schema,
SkillRegistry and schema, RuleMemory and schema, ToolRegistry and schema, every
declared tool implementation manifest, Stage-1/Stage-2/router versions, and the
route, tool, conflict and equivalence policies.

Replay returns a hash-bound `ReplayReport`, never a boolean. It names every
changed component and distinguishes stale data/registries/implementations from
incompatible versions, invalid artifacts and legacy incomplete responses. A
skill or tool response cannot become current through a null or unchanged
FactMemory hash.

RouterStore v1 responses lack complete dependency evidence. Migration marks
them `LEGACY_INCOMPLETE_DEPENDENCY_BINDING`; replay returns
`INCOMPATIBLE_LEGACY_ARTIFACT`. Missing evidence is never synthesized.


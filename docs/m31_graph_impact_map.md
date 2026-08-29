# M-31 graph impact map

Pre-edit graph: 8,522 nodes, 79,588 edges, 504 files, built at exact E9
`e44c073364476d662a0df55d918177aa569d4c54`. Qualified graph queries and source
verification located FactMemory, RuleMemory, SkillRegistry, ToolRegistry,
EducationalCatalogV2, EducationalService, ConversationalTutorService, learner
progress, chemistry adapters, and CLI entry points.

The blast radius is intentionally one-way: Stage-2 education owns chemistry
compatibility and injects a `GenericDomainRuntime`; Stage-2 conversation consumes
the runtime's concept/family mappings; Stage-3 generic packages import no
chemistry. FactMemory and RuleMemory formats are unchanged. The new CLI entry
points and pack builder are offline boundaries.

The final staged implementation graph has 8,745 nodes, 81,518 edges, and 551
files: a delta of +223 nodes, +1,930 edges, and +47 files from E9. It was rebuilt
after all H10 paths were staged, so the previously untracked Stage-3 modules were
included. Final qualified queries were:

- `search GenericDomainRuntime`, `search CapabilityRegistry`, and `search KnowledgeRecord`;
- `callers_of` and `tests_for` the qualified `GenericDomainRuntime` class;
- `callers_of` the qualified `CapabilityRegistry` class;
- `detect-changes --base e44c073364476d662a0df55d918177aa569d4c54 --brief`.

The graph reports four direct runtime consumers, including production
`EducationalService` and the data-only multi-pack test. Source inspection and
the complete test suite remain authoritative where static graph extraction is
ambiguous.

The disposable Karina exact-H10 rebuild reports 5,675 nodes, 54,449 edges, and
420 indexed files, with 421 parser inputs and 5,676 full-build nodes. The local
persistent Windows index reports larger totals because it retains path-history
identities across prior builds. Both values are preserved in
`runs/m31_final_gate/graph_report.json`; the Karina value is the clean-checkout
exact-H10 snapshot.

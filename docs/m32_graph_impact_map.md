# M-32 graph impact map

## Baseline

- Exact E10: `89c14ffcd0107717cc094453e0c86c56f9990212`
- Exact parent H10: `f7d6b024109094c1136950f36488edfdfd6e9e83`
- Branch after baseline check: `exp/stage3-source-to-knowledge-compiler`
- Roadmap SHA-256: `8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`
- Full parser build: 421 files, 5,676 parser nodes, 55,633 parser edges.
- Persistent graph after post-processing: 551 files, 8,745 nodes, 81,518 edges.
- `detect-changes --base 89c14f... --brief`: no changes.
- `impact --base 89c14f... --depth 2 --max-results 50`: no changed or impacted nodes.

The persistent graph includes evidence and generated-history nodes beyond the full
parser count. Both numbers are recorded to avoid treating them as equivalent.

## Exact before queries

The following commands were run after `scripts/update-code-graph.ps1` completed:

```text
code-review-graph status
code-review-graph detect-changes --base 89c14ffcd0107717cc094453e0c86c56f9990212 --brief
code-review-graph impact --base 89c14ffcd0107717cc094453e0c86c56f9990212 --depth 2 --max-results 50
code-review-graph search <symbol> --limit <n>
code-review-graph query callers_of <qualified-symbol>
code-review-graph query callees_of <qualified-symbol>
code-review-graph query tests_for <qualified-symbol>
```

Searches covered `KnowledgeRecord`, `validate_record`, `validate_records`,
`Expression`, `RuleContent`, `ProcedureContent`, `CapabilityRegistry`,
`resolve_capability`, `GenericDomainRuntime`, `InstalledDomainRegistry`,
`EducationalService`, `ConversationalTutorService`, `LearnerProgressStore`,
`TutorOperationJournal`, pending persistence, provider/adapter symbols, catalog
compilation, and provenance.

## Before-state findings

| Closure | Graph evidence | M-32 consequence |
|---|---|---|
| IR records | `KnowledgeRecord` has only the M-31 builder and deserializer as direct callers; no direct `tests_for` result | Add explicit kind/content and semantic mutation suites. |
| IR validation | `validate_records` is called by `validate_pack`; no direct tests were detected | Pack validation is the main authority boundary and needs direct v2 tests. |
| Rule/procedure content | `RuleContent` has two direct constructors; `ProcedureContent` only the deserializer | Replace fallback content mapping and validate symbol/type/procedure flow. |
| Capabilities | `CapabilityRegistry` has 19 inferred tests; resolution is used by builder, CLI, acceptance and domains | Preserve API compatibility while adding provider-derived recursive closure. |
| Domain runtime | Used by M-31 acceptance, educational service and fixture tests; four direct tests | Bind currentness to installed content/provider/capability closure. |
| Installed registry | 23 inferred tests; no direct class caller due to Python dispatch limits | Make stored pack bytes authoritative and audit dependencies/evaluation. |
| Education | 42 inferred tests and eight visible constructors | Introduce a provider interface without weakening legacy chemistry tests. |
| Conversation | 31 inferred tests; dynamic calls are not statically resolved | Remove domain assumptions, persist prepared authority, and stage actual writes. |
| Progress | seven inferred tests | Replace cumulative shared fields with tagged event facts. |
| Operation journal | 21 inferred tests | Add immutable write receipts and pre/post write/advance crash points. |
| Catalog compiler | four direct callers, 25 callees, 23 inferred tests | Keep the frozen trusted chemistry compiler and add a separate provisional pack compiler. |
| Provenance | M-31 pack validation checks binding IDs, while exact source dereference is absent | Acquisition proposals must bind immutable source bytes and exact segment spans. |

Graph results were used only for navigation. Source and tests remain the final
authority, particularly where Python dynamic dispatch caused zero-call results.

## Planned blast radius

- `stage3/knowledge_ir`: schema v2 records, strict serialization, semantic graph validation.
- `stage3/providers` and `stage3/capabilities`: actual provider manifests and recursive receipts.
- `stage3/domains`: content-addressed installation and currentness authority.
- `stage3/acquisition`: bounded input, segmentation, proposal/review/compile/evaluate/replay CLI.
- `stage2/education`, `conversation`, and `progress`: generic provider seam and recovery closure.
- fixtures/tests/scripts/docs: independent sources, goldens, mutation and held-out evidence.

## After state

- After staging the complete implementation/artifact set, the full parser build
  indexed 453 files, 6,023 parser nodes, and 58,898 parser edges.
- Persistent post-processing reported 583 files, 9,091 nodes, and 84,726 edges.
- `detect-changes --base E10 --brief` analyzed 266 changed files, 383 changed
  functions/classes, 42 affected flows, and a 0.85 risk score.
- `impact --base E10 --depth 2 --max-results 5` found 95 impacted nodes and
  intentionally truncated display to five.
- Searches resolved the new `GenericEducationalDomainProvider`,
  `KnowledgeProposal`, and `ProviderRegistry` symbols.
- `callers_of compile_provisional_pack` found the artifact builder, performance
  runner, acquisition CLI, and independent rebuild fixture.
- `callees_of compile_provisional_pack` found 29 direct targets, including alias
  closure, source bindings, record hashing, graph/family construction, and pack
  reload.
- `tests_for compile_provisional_pack` reached the M-32 deterministic rebuild
  fixture; source inspection additionally confirms pack hashes against the
  checked-in build summary.

Exact after queries:

```text
code-review-graph status
code-review-graph detect-changes --base 89c14ffcd0107717cc094453e0c86c56f9990212 --brief
code-review-graph search GenericEducationalDomainProvider --limit 5
code-review-graph search KnowledgeProposal --limit 5
code-review-graph search ProviderRegistry --limit 5
code-review-graph query callers_of <compile_provisional_pack qualified name>
code-review-graph query callees_of <compile_provisional_pack qualified name>
code-review-graph query tests_for <compile_provisional_pack qualified name>
code-review-graph impact --base 89c14ffcd0107717cc094453e0c86c56f9990212 --depth 2 --max-results 5
```

The graph cache records the checked-out commit as E10 because H11 does not yet
exist; staged working-tree nodes are nevertheless indexed. Exact-H11 graph
verification is repeated in both release gates.

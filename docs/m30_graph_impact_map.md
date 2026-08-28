# M-30 project-graph impact map

## Exact-E8 baseline

- Release base: E8 `28fa0e3429ad08650b7a61396bbd62be7201b933`; implementation parent H8 `0a7522cfe104f23981fc971ddde00c993f0f2812`.
- Branch: `exp/stage2-conversational-tutor`, created directly from E8 with a clean tracked tree.
- Index contents: 8,323 nodes, 77,964 edges, 474 files; languages Python, PowerShell and Bash; last content refresh `2026-08-28T20:12:08`.
- The graph database metadata retains E7 as its committed base because H8 was indexed incrementally while it was still a working tree. E8 changes only `runs/m292_final_gate/**`, which the graph excludes. `detect-changes` reports zero changed code symbols for E8's 23 evidence files, so the indexed production/test source is byte-equivalent to exact E8. An incremental `update --brief` confirmed that no E8 source file required reparsing.

## Queries used before edits

- `status`, `detect-changes --brief`, and `update --brief` checked index freshness.
- `search` located each requested symbol before source inspection.
- Fully-qualified `query callers_of`, `query callees_of`, and `query tests_for` were run for `EducationalService`, `EducationalArtifactAuthorityVerifier`, `evaluate_dependency_currentness`, `replay_educational_session`, `ChemistryEducationAdapter`, `FactMemory`, `validate_fact_provenance`, `resolve_source_derivation`, `EducationalCatalogV2`, `EducationalCompilationReceipt`, `EducationalSessionStore`, public DTO/model and `ExplanationPlan`, explanation rendering/verification, controlled education parsing, CLI `main`, session construction/transitions, grading, and hint planning/rendering.
- `impact --depth 2 --base E8` reported no pre-edit changed files, as expected.

## Selected dependency closure

- Current authority: `evaluate_dependency_currentness` has six callers: entry currentness, service session load, explicit educational replay, artifact authority verification, the separated benchmark, and the direct status test. It calls receipt, source-currentness, exercise and graph verification.
- Fact authority: `validate_fact_provenance` is reached by fact graph construction and exercise source-dependency selection; `resolve_source_derivation` has six callers and reaches derivation, source-chain and persistence verification. `FactMemory` has 62 graph-selected tests despite sparse direct constructor edges.
- Catalog/session authority: `EducationalCatalogV2` has 18 dependency-selected tests; `EducationalSessionStore` has 25. The authority verifier is called by service verification and M-29.2 acceptance. Catalog anchoring therefore belongs in the existing education service/authority closure rather than in conversation code.
- Explanation completeness: `render_explanation` has 11 callers and always reaches the trusted plan builder; `verify_explanation` has seven callers and reaches plan verification and canonical re-rendering. `ExplanationPlan` is constructed by the builder, CHECK renderer and deserializer.
- Runtime actions: `grade_answer` has 12 callers, `build_hint_plan` eight and `render_hint` ten. Session start/transition have seven and eleven callers respectively. These remain the only educational authorities used by conversation orchestration.
- Public/controlled boundary: educational CLI `main` reaches 24 callees and has nine selected tests; `parse_educational_request` has two callers and 16 selected tests. New conversation DTOs and parsing will be separate, allowlisted facades over public educational DTOs.

## Graph-selected tests

- Primary: `tests/test_m292_educational_hardening.py`, `tests/test_m291_educational_integrity.py`, and `tests/test_m29_educational_layer.py`.
- Trusted upstream: M-28/M-28.1/M-28.2 chemistry, M-27/M-27.1 router, and M-26/M-26.1 factual-memory suites selected through fact/source/currentness dependencies.
- New M-30 tests will focus on Phase-0 fact replay, catalog anchoring, canonical plans, public text and pending handles, historical authority separation, conversation state and persistence, progress projection/recommendation, isolation, replay, and CLI.

## Components excluded from broad reading

Stage-1 exact interpretation, RuleMemory, SkillRegistry, generic training/data generation, optional neural models, checkpoints, unrelated experiment scripts, non-chemistry domains and prior blind/evidence artifacts are outside the selected closure and architecture freeze. Their public contracts and regression tests remain release gates, but their implementations are not redesign targets.

## Post-implementation update

After adding the new files to the index as intent-to-add, the first incremental
refresh indexed all new package boundaries: 8,501 nodes, 79,264 edges and 504
files at `2026-08-29T00:05:45+03:00`. The pre-refresh depth-2 impact pass over
tracked edits reported 22 changed files, 262 directly changed nodes, 111 impacted
nodes and 29 additional affected files. After the executable acceptance and
complete performance helpers were added, the final refresh contained 8,522
nodes, 79,586 edges and 504 files at `2026-08-29T02:13:46+03:00`; the E8-relative
working-tree analysis covered 79 files, 219 changed functions/classes and 35
affected flows. The graph's generic test-gap list is covered by the new
Phase-0/conversation/progress suites, direct acceptance-helper tests, the selected
M-29/M-29.1/M-29.2 regressions and the final full-suite gate.

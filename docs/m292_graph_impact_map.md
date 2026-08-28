# M-29.2 project-graph impact map

## Baseline index

- Repository SHA: `19a95d3c4d82494f7b9d56c1032ca3ebc9b5edd0` (E7).
- Branch at analysis time: `exp/stage2-educational-hardening`, created directly from E7.
- The pre-existing index was stale at E6 `bc02e70395f3b556d969c697787ef2d57ed2ff4a` with 8,145 nodes, 75,725 edges and 452 files.
- It was refreshed incrementally with `code-review-graph update --base bc02e70395f3b556d969c697787ef2d57ed2ff4a --brief`.
- Exact-E7 index after refresh: 8,238 nodes, 76,873 edges, 465 files; `built_at_commit=19a95d3c4d82494f7b9d56c1032ca3ebc9b5edd0`, updated `2026-08-28T18:12:12`.

## Queries used

For every target below, the initial pass used `search`, then `query callers_of`, `query callees_of`, and `query tests_for` with the fully qualified symbol where a short name was ambiguous. `detect-changes --brief` was used before refresh. The post-change pass will use `update --brief`, `impact`, and the same relationship queries.

Queried targets:

- `EducationalService`, including `handle_controlled`, all learner actions, `replay`, and `verify`;
- `EducationalCatalogV2`, `compile_catalog_v2`, `_split_manifests`, and `_verify_splits`;
- `EducationalSessionStore` and `reconstruct_and_validate`;
- `verify_derivation_graph` and `build_result_graph`;
- `render_explanation`, `render_check_explanation`, `grade_answer`;
- `build_hint_plan`, `render_hint`, and `verify_hint_no_answer_leakage`;
- `replay_educational_session`;
- `PresentedExercise`, `TutorSession`, and `EducationalCompilationReceipt`;
- `evaluate_independent_fixtures`;
- `src/ai_brain/stage2/education/cli.py::main` and controlled educational routes.

## Impact and callers

- Graph semantics: `verify_derivation_graph` has 14 direct callers, including the chemistry graph adapter, both graph builders, explanation/check rendering, grading, hint planning/rendering, M-29/M-29.1 benchmarks, acceptance mutation batteries, and artifact semantic validation. This is the central operation-contract enforcement point.
- Runtime facade: `EducationalService` is exercised directly by public-boundary and controlled-route tests. Its action methods are consumed by the CLI and `handle_controlled`; the controlled handler dispatches explain, create, submit, hint, and solution actions.
- Persistence: `reconstruct_and_validate` is called by `EducationalSessionStore.save_artifact`, `get_artifact`, and `verify`. Authority-aware verification therefore belongs beside this structural path, injected by the service layer rather than hidden globally.
- Replay/currentness: `replay_educational_session` is called by `EducationalService.replay` and already reaches receipt verification, live source replay, graph verification, session events, and store verification. Its semantic dependency checks are the seed for a bounded shared currentness core.
- Explanation/grading/hints: `render_explanation` is called by service explain/confirm/solution and hint rendering; `grade_answer` is called by submit, benchmarks and independent evaluation; hint plan/render are called by the service, benchmarks and independent evaluation.
- Catalog/splits: `compile_catalog_v2` is called by the admin script and CLI. `_split_manifests` feeds compilation; `_verify_splits` is called by catalog verification.
- DTO/session models: `PresentedExercise` is constructed by presentation and deserialization; `TutorSession` by start/apply/deserialization; `EducationalCompilationReceipt` by both compilers and deserialization.
- CLI: `main` calls service open plus every learner action, replay, verify, backup/restore, and offline compilation.

## Dependency-selected tests

Primary existing tests selected by the graph:

- `tests/test_m291_educational_integrity.py`: graph v2 mutations, public presentation, confirmed authority, semantic store tamper, controlled routes, terminal transitions, and independent diagnosis;
- `tests/test_m29_educational_layer.py`: graph tamper, exact operation coverage, bilingual explanations, grading, hint leakage, sessions/replay/backup/restore, and controlled routing;
- trusted upstream regressions in `tests/test_m28_chemistry.py`, `tests/test_m281_chemistry_integrity.py`, `tests/test_m282_chemistry_provenance.py`, `tests/test_m27_unified_router.py`, `tests/test_m271_router_hardening.py`, `tests/test_m26_factual_memory.py`, and `tests/test_m261_factual_integrity.py`.

New focused tests cover operation-only rehashed mutations, stale runtime action matrices, authority-aware artifact reconstruction, public DTO serialization, exact split universes, honest diagnosis metrics, schema rejection, and bounded currentness performance.

## Intentionally excluded from broad rereading

The graph isolated the work to Stage-2 education, the chemistry education adapter and its trusted dependency interfaces. Stage-1 acquisition/training, neural models, generic data-generation pipelines, unrelated CLI commands, and non-chemistry domains do not need broad source rereads. Concrete edits and graph claims will still be checked with targeted `rg`, source inspection, and tests because static graph edges are advisory.

## Post-change state

- The first incremental refresh updated 22 tracked files (533 nodes and 5,635 edges). New files were then marked intent-to-add so the index would not omit the new modules; the second incremental refresh added 9 files, 63 nodes and 916 edges.
- A final incremental refresh after the orphan-artifact authority rule updated 4 affected files (40 nodes and 312 edges).
- Final working-tree index: 8,323 nodes, 77,964 edges and 474 files, updated `2026-08-28T20:12:08` on `exp/stage2-educational-hardening`, with E7 still recorded as the committed base SHA and the working-tree changes indexed incrementally.
- `impact --depth 2` reported 291 directly changed nodes, 57 impacted nodes within two hops, and 19 additional affected files. The impact command also reported legacy E7-to-working-tree evidence/report paths as changed because its default base predates E7; direct `git diff E7` remains the release scope authority.
- Post-change relationship checks found six callers of the shared dependency-currentness core: entry currentness, runtime session load, explicit replay, authority verification, the separated benchmark and the direct status test.
- The canonical operation verifier has exactly two production callers: graph construction (`make_node`) and graph semantic verification (`_verify_node`). This makes incompatible kind/operation pairs impossible both at creation and at trust validation.
- The new authority verifier is reached by `EducationalService.verify` (confirmed in source because the graph reports a short-name ambiguity for `verify`) and directly by M-29.2 acceptance; its session closure calls the same currentness core.
- `tests_for EducationalService` now returns 31 direct/indirect tests, including the new stale-before-write, rehashed presentation, public DTO, complete authority closure and forged grading-closure tests.
- Final dependency-selected execution set remains the three educational test modules plus the prior trusted chemistry, factual-memory and router regressions listed above. The complete suite is still the final release gate.

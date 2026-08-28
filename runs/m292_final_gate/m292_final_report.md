# M-29.2 final exact-H8 report

## Release identity and elapsed time

- Result: **PASS**. M-29.2 is complete; M-30 is not implemented.
- Branch: `exp/stage2-educational-hardening`.
- H8: `0a7522cfe104f23981fc971ddde00c993f0f2812`.
- Exact parent chain: H8 -> E7 `19a95d3c4d82494f7b9d56c1032ca3ebc9b5edd0` -> H7 `bebc4d0d150646ac65142cd2e5dad2e049587a88`.
- H8 tree: `25c664bf7c24f462027730ff657eca5627794cb2`.
- Measured execution window from exact-E7 baseline start through final exact-SHA provenance capture: `2026-08-28T18:17:37+03:00` to `2026-08-28T21:23:34+03:00`, 3h 05m 57s. Individual gate durations are retained in their logs.
- E8 is the evidence-only commit containing this report; its SHA is intentionally supplied after commit creation rather than self-referentially embedded here.

## Trust contracts changed in H8

1. A canonical `GraphNodeKind`/operation allowlist is shared by graph builders and semantic verification, including dimension-aware mole/Avogadro rules and real unit-conversion semantics.
2. Precompiled explanation, exercise presentation, submission/grading, hint, solution and explicit replay share a bounded live-currentness core and exact typed `EducationalReplayStatus` failure.
3. Structural persistence verification is separated from service-aware authority verification. Grading, hint plan/hint, CHECK/FULL/solution explanations, presentations, receipts, sessions and event closure are deterministically reconstructed from their authorities.
4. Hint and CHECK artifacts bind the exact grade/diagnosis authority; solution artifacts bind the pre-event session state and real attempt.
5. Learner-facing service, CLI and controlled routes return immutable allowlisted DTOs and exclude internal graph/session/artifact/provenance/split/receipt data.
6. Store, catalog, graph, exercise, grading, hint, explanation, tutor and replay schemas are advanced to strict v3 with explicit v2 rebuild/archive behavior.
7. Split verification requires exact universe coverage and truthful axis names. Diagnosis fixtures and metrics now describe synthetic cross-implementation evaluation without claiming human review.
8. Service backup verifies structural and authority layers before copying; restore performs both after reconstruction.

No M-30 orchestration, learner-progress memory, neural surface, model training, unrestricted chemistry, automatic trusted-memory writes, network path, diagnosis-authority expansion or targeted hints from partial/ambiguous diagnoses were added.

## Project/code graph workflow

- Initial local index was stale at E6: 8,145 nodes, 75,725 edges, 452 files. An incremental refresh produced an exact-E7 index: 8,238 nodes, 76,873 edges, 465 files, updated `2026-08-28T18:12:12`.
- Queries: `search`, fully qualified `callers_of`, `callees_of`, `tests_for`, `detect-changes`, incremental `update`, and post-change `impact --depth 2` for every task-specified education service, catalog, persistence, graph, explanation, grading, hint, replay, model, compiler, split, evaluation, CLI and controlled-route node.
- Final incremental working-tree index: 8,323 nodes, 77,964 edges, 474 files, updated `2026-08-28T20:12:08`; 291 directly changed nodes, 57 depth-two impacted nodes and 19 additional affected files.
- Key post-change relationships: six callers of the shared currentness core; exactly two production callers of canonical operation verification (`make_node`, `_verify_node`); 31 direct/indirect tests for `EducationalService`.
- Graph-selected scope was Stage-2 education, the chemistry education adapter and trusted chemistry/factual-memory/router interfaces. Stage-1, neural/training code, unrelated CLIs and non-chemistry domains did not require broad rereading.

## Exact-E7 baseline

- Full suite: 739/739, 1,250.73s.
- Prior trusted regressions: 274/274, 989.62s.
- M-29.1 acceptance: PASS.
- Catalog: 2,000 entries, VERIFIED; store schema v2 VERIFIED.
- Official M-29.1 10k throughput: Windows `180.7212096614628/s`; Karina `946.4111772541065/s`.
- Official M-29.1 offline catalog compilation: Windows `184.038459s`; Karina `23.665411s`.
- Frozen M-29.1 catalog/store/evidence diffs: zero.

## Exact-H8 Windows gate

- Environment: Windows host `IBICZA`, Python 3.12.13, uv 0.12.3.
- Full suite: **750/750**, 898.43s.
- Exact prior trusted regression set: **274/274**, 759.83s.
- M-29.2 acceptance: **PASS**.
- 10k identical comparison benchmark: `533.2092676228988/s`, 295.05% of the official E7 Windows rate; runtime chemistry executions: 0.
- Separated mean latency: presentation 314.7723ms; grading 275.074767ms; generic hint 253.652364ms; targeted hint 256.458539ms; replay/currentness 277.217470ms; full service verify 11,116.8289ms.
- Offline catalog compilation: 136.370637s measured by the benchmark, 137.859618s in the independent rebuild.

## Exact-H8 Karina gate

- Environment: host `karina`, detached exact-H8 worktree `/home/ibicza/m292-exact-0a7522c/repo`, Python 3.12.14, pytest 9.1.1, exact-worktree source selected with `PYTHONPATH=<exact>/src`.
- Full suite: **750/750**, 216.48s.
- Exact prior trusted regression set: **274/274**, 161.19s.
- M-29.2 acceptance: **PASS**; its JSON is byte-identical to Windows, SHA-256 `6c562f5c5ca7e1128e1a7ba088457ebd30721d7cd5c77f6721fd93a566ae91c7`.
- 10k identical comparison benchmark: `1480.6046522776355/s`, 156.44% of the E7 Karina rate; runtime chemistry executions: 0.
- Separated mean latency: presentation 36.6863ms; grading 40.0223ms; generic hint 41.1258ms; targeted hint 41.2376ms; replay/currentness 42.2009ms; full service verify 4,237.7708ms.
- Offline catalog compilation: 23.533216s measured by the independent rebuild; 24.047069s measured inside the benchmark.

Both platforms exceed the 75% E7 throughput floor. The comparison benchmark is unchanged; offline compilation and all newly added runtime stages are reported separately.

## Acceptance details

- Authority: 0 hidden runtime executions; 0 unconfirmed executions; confirmed calculation exactly 1; 2,000 offline receipts and 0 receipt-less executions.
- Graph mutation battery: 2,000 semantic mutations across 10 categories, including 200 operation-only rehashed mutations; accepted 0. Focused tests cover every real operation-bearing node kind, and valid catalog graphs are accepted.
- Currentness matrix: 60 cases = 10 stale categories x 6 actions. Categories: domain, FactMemory, source chain, tool, claim, evidence, source, upstream source, compilation receipt, answer key/graph. Actions: precompiled explain, present/create, submit/grade, hint, solution, replay. Wrong status 0, mutations/events/artifacts 0, hidden executions 0.
- Artifact semantic tampering: 10 checksum-valid/rehashed categories, accepted 0: PresentedExercise, CompilationReceipt, GradingResult, HintPlan, HintArtifact, CHECK_ONLY, full explanation, solution session binding, TutorSession and TutorEvent/event references.
- Public serialization: 1,000 probes; hidden answer/graph/receipt/counterfactual/split/provenance leaks 0; no learner-facing internal session or artifact objects.
- Sessions: 30 transition cases; valid rejections 0, invalid acceptances 0; terminal and stale-before-write behavior preserved.
- Import boundary: 42 trusted Python files scanned; torch imports 0, network imports 0, hidden executor 0.
- Structural store verification: `STRUCTURALLY_VERIFIED` (schema 3, 30 artifacts, 10 events, 4 sessions). Authority layer: `AUTHORITY_VERIFIED`.

## Split universes and diagnosis

Catalog universe is 2,000 semantic entries and every entry has membership in all seven manifests. All development/final intersections are 0, saved counts match recomputation, and unions exactly cover the universe.

- True content holdouts: `FORMULA_STRUCTURE_HOLDOUT`, `ELEMENT_COMBINATION_HOLDOUT`, `NUMERIC_RANGE_HOLDOUT`, `UNIT_DIRECTION_HOLDOUT`, `MULTI_STEP_COMPOSITION_HOLDOUT`.
- Deterministic evaluation partitions: `TEMPLATE_KEY_PARTITION`, `LANGUAGE_ASSIGNMENT_PARTITION`.
- Separate diagnosis universe: `SYNTHETIC_DIAGNOSIS_FIXTURE_PARTITION`, 1,200 fixture IDs, schema 2, evaluation kind `SYNTHETIC_CROSS_IMPLEMENTATION`, `human_review_status=NOT_REVIEWED`.

Diagnosis results: micro precision `0.7307692307692307`; macro precision over categories with predictions `0.7`; macro recall `0.2736842105263158`; coverage `0.39`; abstention `0.61`; unclassified 732; ambiguous 15; wrong-confident 0; wrong-targeted-hint 0; grading-status mismatch 0. Precision is null/undefined for categories with zero predictions.

## Catalog, rebuild and recovery

- Catalog: 2,000 entries, 2,000 distinct semantic keys, 2,000 graphs, 2,000 compilation receipts, 1,900 receipt-bound tool executions.
- Internal catalog hash: `23747602972c6f9d7108c4460c542eddf07ea2ad4ed56ba860b95c3aab254e79`.
- File size: 53,413,674 bytes; SHA-256 `fa4a109ee7039933d3f0d8cb53e9cc853766a7d682b85b46fc7bc5825cedc7a1`; LF-only with exactly one terminal LF.
- Independent Windows and Karina rebuilds have the same SHA-256, size and newline contract, proving byte identity.
- Backup/restore on both platforms verified structural and authority layers before backup and after restore: 30 artifacts, 10 events, 4 sessions, schema 3, AUTHORITY_VERIFIED.

Two preliminary harness invocations touched a tracked chemistry SQLite audit file (one during Windows development before H8 and one excluded Karina backup diagnostic). Each file was restored byte-for-byte from its exact commit before any qualifying gate. The final Windows H8 checkout and Karina H8 worktree both report the tracked pack at its Git-object SHA and clean status; all qualifying runners use disposable chemistry copies. The excluded Karina diagnostic is retained for transparency and is not counted as a gate result.

## Release integrity and remaining limitations

- The H8 tree is clean on Windows and Karina after all gates. Karina's pre-existing main checkout remains at `0a231f4267bd501cc45159e7070d94262b4de87a` with its original unrelated dirty files; it was not used or modified by this task.
- `gpt` and `origin/gpt` remain `0a231f4267bd501cc45159e7070d94262b4de87a`. H7, E7 and all Stage-1 tags are unchanged. No merge was performed.
- No moral, moderation, refusal, political, ideological or topic restriction was added. Acceptance records `content_policy_added=false` and `m30_implemented=false`.
- Evidence-only qualification requires every H8->E8 changed path to be under `runs/m292_final_gate/**` and zero changes under `src/**`, `tests/**`, `scripts/**`, catalog, schemas, fixtures or runtime configuration; the exact automated result is recorded after staging/commit.
- Remaining scope is deliberate: chemistry-only deterministic education, conservative diagnosis authority, synthetic non-human-reviewed diagnosis fixtures, no conversational orchestration or learner-progress memory. Those belong to later work.

On these results, transition to M-30 is permitted; M-30 itself is not declared ready or implemented.

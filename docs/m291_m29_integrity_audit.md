# M-29.1 audit of M-29 educational integrity

Baseline: evidence commit `bc02e70395f3b556d969c697787ef2d57ed2ff4a`, implementation parent `f82dabfd5380a9e7a7a64f8ac9ffde0e47fdbf4e`.

The 20 audited paths and v2 dispositions are:

1. `src/ai_brain/stage2/domains/chemistry/education/graph_adapter.py::ChemistryEducationAdapter.tool_graph` directly executed the registry. It now fails closed; only `education/compiler.py::compile_answer_key` owns the offline direct call.
2. `src/ai_brain/stage2/education/service.py::EducationalService.explain_tool` formerly hid execution. It now loads a verified precompiled graph or returns PREPARED; `confirm_explanation` is the one-execution path.
3. `src/ai_brain/stage2/education/exercise_generation.py::generate_exercise` formerly derived answer keys at runtime. Runtime selection now requires `EducationalCatalogV2`.
4. `src/ai_brain/stage2/education/acceptance.py::run_educational_acceptance` hardcoded hidden execution. The legacy field is `NOT_MEASURED_M29_LEGACY`; `acceptance_v2.py::_authority` uses an execution monitor.
5. `src/ai_brain/stage2/education/graph_validation.py::_verify_node` did not bind `exact_inputs` to ordered input outputs. V2 uses typed canonical binding.
6. `graph_validation.py::_verify_operation` had incomplete unit/dimension checks. V2 has a closed dimension enum, unit table and exact operation contracts.
7. `graph_validation.py::_verify_rounding` did not independently recompute display rounding. V2 reconstructs `ChemistryRoundingSpec` and recomputes it.
8. `src/ai_brain/stage2/education/explanations.py::verify_explanation` allowed unsupported additions. V2 regenerates exact text from a hashed finite plan.
9. `explanations.py::render_explanation` exposed the root for CHECK_ONLY. Generic CHECK_ONLY/HINT_ONLY rendering is refused; check text requires a `GradingResult`.
10. `src/ai_brain/stage2/education/replay.py::replay_educational_session` relied on snapshots. V2 calls live chemistry replay or revalidates live fact provenance.
11. `src/ai_brain/stage2/education/persistence.py::EducationalSessionStore.verify` checked storage integrity without complete semantics. V2 uses the closed artifact registry and cross-artifact checks.
12. `src/ai_brain/stage2/education/service.py::EducationalService._load` consumed unchecked dictionaries. It now receives typed, semantically verified artifacts only.
13. `service.py::create_exercise`, the controlled route and CLI exposed internal instances. They now return/serialize only `PresentedExercise`.
14. `exercise_generation.py::derive_exercise_variant` changed identity metadata only. `instantiate_variant` changes a bounded RU/EN question template while preserving a semantic key.
15. `exercise_generation.py` assigned split axes by seed. V2 membership comes from immutable compiler-generated manifests with persisted zero intersections.
16. M-29 diagnosis acceptance reused production counterfactual generation. `independent_evaluation.py` reads a separately generated 1,200-case fixture pack.
17. M-29 hint acceptance did not pass diagnoses. V2 passes actual grading diagnoses and reports independently tested targeted hints.
18. M-29 hint leakage was literal-only. `hint_validation.py` covers Unicode, scientific notation, equivalent units, intervals and structured composition.
19. `graph_builder.py` collapsed or failed interval molar mass. V2 propagates lower/upper bounds through terms, sums, conversion and rounding.
20. `sessions.py::apply_event` allowed unrestricted transitions. V2 has an explicit state/event table, terminal states and event-order enforcement.

No M-29 evidence or report was overwritten.

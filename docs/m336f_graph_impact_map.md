# M-33.6f graph impact map

The graph was rebuilt on branch `exp/stage3-m336f-java-trust-closure-freeze-v5` at exact R20 before broad reading. Baseline status: 14,079 nodes, 100,581 edges, 1,043 files, commit `8e0b542bd180`.

The navigation pass used `status`, `detect-changes`, `search`, qualified `callers_of`, `callees_of`, `tests_for`, and depth-two `impact`. The inspected routes were acquisition, source indexing, proposal/evidence creation, classpath closure, diagnostic scoping, production trust binding, packability, replay, independent goldens, trust/evidence confusion, census/selector feasibility, seals, runtime, platform comparison and readiness.

The pre-refresh tracked-file detector saw 15 modified files, 42 changed functions/classes, 45 affected flows, 33 graph test gaps and risk `0.75`. Untracked R21 modules were not yet visible to that detector, so every graph finding was checked against source with `rg` and dedicated tests.

The implementation boundary is:

- `java_production_compiler.py`: deterministic JDK 21 probe, normalized diagnostics, UTF-16-to-canonical-UTF-8 locations and fail-closed trust gate;
- `m336f_compilation_closure.py` and `m336f_selection.py`: source dependency closure, pre-selector witness feasibility and one-shot selection;
- `java_production.py` and replay: compiler evidence bound into every trust decision and standalone reproduction;
- `m336f_field_evidence.py`: independent exact row comparison;
- `m336f_evaluation_artifacts.py`, `m336f_license_evaluation.py` and `m336f_contracts.py`: semantic/telemetry split and strict producer coverage;
- shared gate/readiness modules: one frozen count-first threshold manifest.

The final pre-commit refresh status is 14,083 nodes, 100,725 edges and 1,043 indexed files; the full build parsed 1,044 files and constructed 15,430 pre-postprocess nodes and 102,696 edges. The final detector reports 75 changed files, 266 changed functions/classes, 85 affected flows and risk `0.85`. The graph still omits untracked R21 symbols from its persistent baseline until the commit exists, so new modules are additionally covered by dedicated tests and direct source inspection; an exact post-commit refresh is required before authoritative qualification.

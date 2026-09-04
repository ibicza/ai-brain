# M-33.6 graph impact map

Graph base: E14 `6b0c31e6e6f987216923a66e332370aeeffa9f48`.

Before Phase 0 the local graph contained 16,008 nodes, 111,642 edges, and 1,051
files. `status` and `detect-changes --base` reported no change at the exact base;
`impact --depth 2` was empty before edits.

The first navigation pass used `search`, `callers_of`, `callees_of`, `tests_for`, and
`impact --depth 2` around `ingest_bundle`, `verify_bundle`, SourceDocument and
SourceBundle hashing, `compile_provisional_pack`, `JavaCanonicalCallableIdentity`,
packability build/verification, the production pipeline and verifier, component
manifest, aliases, role/freeze protocols, pre-freeze V3, denylist, selector, and
production/evaluator orchestration. `verify_bundle` had five direct callers and 31
graph-selected tests at E14.

The exact post-edit queries were:

```text
code-review-graph status
code-review-graph detect-changes --base 6b0c31e6e6f987216923a66e332370aeeffa9f48
code-review-graph query callers_of src/ai_brain/stage3/acquisition/compiler.py::compile_provisional_pack
code-review-graph query callees_of src/ai_brain/stage3/acquisition/java_production.py::run_java_acquisition_pipeline
code-review-graph query tests_for src/ai_brain/stage3/acquisition/java_production_replay.py::verify_compiled_java_production_standalone
code-review-graph impact --depth 2
```

The rebuilt pre-F15 graph contains 16,027 nodes, 112,000 edges, and 1,051
files: +19 nodes, +358 edges, and no file-count change. Against E14 the graph
reported 14 changed tracked files, 47 changed functions/classes, 24 affected
flows, 42 graph test gaps, and risk 0.85. The focused queries found 16 callers of
`compile_provisional_pack`, 13 callees of `run_java_acquisition_pipeline`, and 38
direct-or-indirect test candidates for standalone replay verification. Because
untracked Phase-0 modules are not represented reliably by the incremental diff,
the graph findings were verified with source search and the explicit M-33.6 test
suite instead of treating graph coverage as proof.

The selected edit closure is limited to Stage-3 Java acquisition/compiler identity,
packability, source selection, diagnostic classification, freeze policy, executable
orchestration, and their tests/docs. Stage 1, GPT integration, unrelated domains,
memory systems, UI, and model-training paths were excluded from broad reading.

Production starts from `m336_run_oracle_free_production.py` and its static local
import closure. That command imports neither golden loading nor production evaluator
code, accepts no evaluator argument, forbids evaluator/oracle/golden file reads,
blocks subprocesses and sockets, and seals the candidate before the separate
evaluator command can create oracle artifacts.

Graph-selected direct regressions include the M-33.5 candidate-pack/runtime test,
the M-34.4 oracle-free production/replay tests, and the M-34 blocker identity and
packability tests. They are supplemented by `tests/test_m336_fresh_java_freeze.py`
and the complete suite because `tests_for` contains low-confidence indirect edges.

The graph was rebuilt immediately before F15. Production cannot reach evaluator or
golden code because the standalone production entry point has a statically checked
local-import closure, exposes no evaluator/golden argument, installs file-read,
subprocess, socket, and import guards, and seals replay before the independent
evaluator command exists. The pre-F15 disclosed regression measured zero evaluator
dependencies and zero forbidden/golden reads on both platforms.

# M-33.5 graph impact map

Graph base: E13 `f1599585c7b45e73eb3ba3cd9113155188eb6d26`.

The first graph status (stale F13 cache) reported 794 files, 12,927 nodes and
98,358 edges. The exact-E13 rebuild reported 902 indexed files and 14,140
primary nodes during build; post-build status reported 1,032 files, 15,863
nodes and 109,791 edges. The graph tool also reported 14,831 unique loaded
nodes. The final I14 working-tree rebuild indexed 902 source files and reported
14,153 primary nodes/84,665 primary edges; post-processing loaded 14,844 unique
nodes and 110,028 edges, while final status reported 1,032 files, 15,876 nodes
and 110,028 edges. These tool-native counters are recorded without conflating
them.

Queries run before broad reading: `status`, `detect-changes`, `impact --depth 2`,
and `search`, `callers_of`, `callees_of`, `tests_for` for `ingest_bundle`,
`run_java_acquisition_pipeline`, `detect_java_identity_conflicts`,
`detect_java_production_identity_conflicts`, `compile_provisional_pack`,
`verify_java_git_freeze_protocol`, `_aliases`, `_content_aliases`, `_slug`, and
`_rewrite_content`.

Dependency paths selected for change:

- source paths -> `ingest_bundle` -> `SourceDocument` -> `SourceBundle` -> Java
  source index -> segments -> proposals -> evidence -> decisions;
- Java declaration descriptor -> canonical callable identity -> conflict closure
  -> packability -> final trust -> pack record ID;
- exact references -> content rewrite, while search aliases -> retrieval only;
- Git H-stage paths -> immutable artifact roles -> protected disclosure overlap.

Selected tests cover M-34.1 through M-34.4 plus the M-33.5 identity,
determinism, packability, alias and role verifier suite. Broad reading excluded
Stage 1, neural execution, tutor conversation policy, episodic memory and
relationship memory because no dependency path reached them.

The I14 working-tree graph was rebuilt after the public data models, runtime
alias API and state-audit boundary were complete. `detect-changes` then reported
23 changed indexed files, 57 changed functions/classes, 43 affected flows, 45
tool-inferred test gaps and risk score `0.80`; its highest-risk boundaries are
the external Java oracle launcher, production batch verifier and standalone
replay. The targeted and exact-I14 test selections exercise those boundaries.

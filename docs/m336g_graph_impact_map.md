# M-33.6g graph impact map

The graph was rebuilt from exact R21 before broad source reading. Baseline status was 14,263 searchable nodes, 103,274 edges, and 1,062 files; the full post-process reported 15,610 nodes, 105,280 edges, and 1,063 parsed files. `detect-changes` identified the R20..R21 historical range as high risk, so its output was used for orientation rather than treated as a clean-working-tree diff.

Graph search, callers, callees, tests, and depth-2 impact identified these primary boundaries:

- `compiler.py::compile_provisional_pack`: 18 direct callers and the public pack writer.
- `java_production_replay.py::build_java_production_replay_artifact`: the source-bearing R21 producer.
- `java_production_replay.py::verify_compiled_java_production_standalone`: the legacy source reconstruction verifier.
- `domains/loader.py::load_pack` and `domains/registry.py::_dependency_items`: load/install consumers.
- `java_jdk_provider.py::verify_m336_jdk_provider`: the host-path receipt producer.
- `m336d_leak_scan.py::scan_fresh_source_leaks`: the independent public-tree leak gate.

The R22 blast radius therefore includes the compiler, loader, installation dependency handling, replay verification, JDK evidence, leak scan, production scripts, and their regression tests. Concrete `rg` and source inspection verified every graph result before editing.

The post-change rebuild completed with 14,275 searchable rows, 13,213 unique nodes, 103,418 status edges, and a full post-process of 15,622 nodes / 105,428 edges across 1,063 indexed files. The added publication/replay/staging modules did not introduce unresolved or ambiguous Python imports.

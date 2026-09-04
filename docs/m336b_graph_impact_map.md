# M-33.6b graph impact map

Roadmap SHA-256: `8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`.

The graph was rebuilt at exact E16 `01fac1522c2cf694e440378b2bb58736ba4b9e28`. Before implementation it contained 16,249 nodes, 115,007 edges, and 1,075 files. The final pre-F17 incremental state contains 16,292 nodes, 115,456 edges, and 1,075 files. Untracked new files enter the committed graph on the exact-F17 update.

Queries executed were `status`, `detect-changes`, searches for every mandated symbol, `callers_of`, `callees_of`, `tests_for`, and `impact --depth 2`. The initial eight-file impact query found 118 changed target nodes, 47 impacted nodes within two hops, and 15 additional files.

The production-provenance closure runs from `MavenCentralProvenanceProvider` and `ScmRevisionProvider` through correspondence v2, envelope v2, artifact qualification, and the candidate-set verifier. The selection closure runs only from the verified distinct eligible-root set to the frozen M-33.6b selector. The disclosure closure combines the historical denylist, append-only data registry, role manifest, typed claim extraction, and schema-bound verifier.

Graph-selected tests were the M-33.5 determinism, M-33.6 freeze, M-33.6a repair, and M-33.6b provenance suites. Broad reading intentionally excluded unrelated Stage 1 model code, GPT integration, non-Java domain packs, and UI code. Source and tests remain the authority where graph edges are incomplete.

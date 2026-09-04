# M-33.6c graph impact map

The graph-first pass was run from exact E17 `1541805f9cd6c19ff9c372afeefbd41148217736` before broad source reading. The verified base graph contained 1,090 files, 16,391 nodes and 116,758 edges. Its recorded branch and commit both matched E17.

The exact query forms were:

```text
code-review-graph status
code-review-graph detect-changes --base 1541805f9cd6c19ff9c372afeefbd41148217736
code-review-graph search <mandated-symbol-or-artifact>
code-review-graph query callers_of <qualified-symbol>
code-review-graph query callees_of <qualified-symbol>
code-review-graph query tests_for <qualified-symbol>
code-review-graph impact --depth 2 --base 1541805f9cd6c19ff9c372afeefbd41148217736
```

Search subjects were `resolve_license_evidence`, `license_text_evidence`, `normalize_license_text`, `inspect_source_archive`, `parse_maven_pom`, `qualify_artifact`, `qualify_candidate_set`, `acquire_and_qualify_maven_source_candidates`, `ScmRevisionProvider`, `SourceArtifactProvenanceEnvelope`, `FinalArtifactRole`, `classify_final_artifact_role`, `extract_disclosure_claims`, the H17 assembler and role manifest, both missing H17 root artifacts, and the final Java production/evaluator orchestration. Short-name results were resolved to qualified symbols before relationship queries.

The license decision path is Maven POM/archive inspection -> document-role classification -> frozen SPDX template matching -> typed evidence fusion -> four-axis source authority. Candidate qualification adds provenance-envelope verification, per-entry correspondence and source-use authorization before disclosed-only selection.

The artifact path is the contract registry -> path match -> strict field/schema validation -> role-manifest view and disclosure-claim view -> hypothetical H-tree and immutable H17 verification. `java_freeze_roles.py` now delegates those views to the registry instead of maintaining independent path, role and protected-field tables.

The initial depth-two impact covered 150 directly changed nodes, 96 impacted nodes and 27 additional files. Graph-selected tests were supplemented by the explicit M-33.5, M-33.6, M-33.6a, M-33.6b and M-34.1 through M-34.4 regression modules because scripts and JSON artifacts are not completely represented by call edges.

Broad reading excluded Stage 1, educational/tutor runtime, non-Java domain packs, neural/model modules, UI code and roadmap M-34 Episodic and Relationship Memory. Only the provenance, license, Java semantic trust, freeze-contract, registry and final-gate paths named above were inspected.

The pre-I18 graph rebuild completed on the implementation worktree with 1,090
files, 16,389 nodes and 116,748 edges. The final depth-two comparison against
exact E17 reported 62 tracked changed files, 268 directly changed nodes, 207
impacted nodes and 71 additional affected files. Untracked M-33.6c modules,
schemas, documentation and generated development evidence were also inspected
directly because the graph's Git comparison does not treat them as committed
I18 inputs until staging.

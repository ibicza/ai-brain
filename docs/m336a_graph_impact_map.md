# M-33.6a graph impact map

Exact base: E15 `b4f8b881ab15e995c8df9e17e4704f5dec34e028`. The graph was rebuilt before broad reading. Before: 16,131 nodes, 113,549 edges, 1,066 files; `detect-changes --base E15` was empty.

Queries: `status`; `detect-changes --base b4f8b881ab15e995c8df9e17e4704f5dec34e028`; searches for `_license_receipt`, `JavaSourceFamily`, `frozen_m336_final_source_selector_policy`, `select_final_java_sources`, `m336_selector_receipt`, `FinalArtifactRoleManifest`, `build_final_artifact_role_manifest`, `verify_role_aware_disclosure`, `derive_protected_disclosure_tokens`, `verify_m336_git_freeze_protocol`, and the timeout node; `callers_of` and `callees_of` for `_license_receipt` and disclosure verification; `tests_for`; and `impact --depth 2`. Impact reported 13 evidence files and zero indexed nodes/flows, so source search and tests were used to resolve the unindexed-script limitation.

The call chain was download -> `_license_receipt` -> embedded substring search -> exception. The exception preceded root accumulation and the selector. Role serialization was `build_final_artifact_role_manifest` -> `asdict` -> canonical JSON, while verification compared parsed JSON lists directly to dataclass tuples. Disclosure was role classification -> recursive key-name scanning -> string containment against F15.

The repair adds a generic provenance model, Maven adapter, qualification gate, accumulated denylist, typed manifest codec, typed disclosure claims, and batched Git blob reads. Selected tests cover the new layer plus M-33.5/M-33.6 regressions. Broad reading excluded Stage-1, neural training, unrelated domain packs, and educational routing; the M-29 chemistry builder was read only for the exact timeout investigation.

After the final exact-I16 structural rebuild: 16,249 nodes, 115,007 edges, 1,075 files. The E15-relative graph detected 37 changed files, 127 changed functions/classes, 14 affected flows, 80 graph-level test gaps, and risk score 0.85. The final patch inventory, source inspection, and targeted/full tests remain the authoritative complement to graph-level heuristics.

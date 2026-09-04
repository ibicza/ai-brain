# M-33.6 failure forensics

The three coordinates were `com.google.guava:guava:33.4.8-jre`, `org.apache.commons:commons-collections4:4.5.0`, and `com.github.ben-manes.caffeine:caffeine:3.2.0`, at the exact Maven Central paths frozen in F15.

| Candidate | Bytes | source JAR SHA-256 | entries / Java | embedded license | POM SHA-256 |
|---|---:|---|---:|---|---|
| Guava | 1,847,395 | `9d3c6aad893daac9d4812eb9fa4c3f7956a9f2e472eb7df2fea0e467fed7e766` | 653 / 615 | `META-INF/LICENSE` | `04365d4b6ef22c8cf9349fe628069fc3e81a2c838351402ef4e95f9e757beebc` |
| Commons Collections | 804,556 | `75f1bef9447cce189743f7d52f63a669bd796ae19ca863e1f22db1d5b6b504a6` | 391 / 359 | `META-INF/LICENSE.txt` | `c700f998e1d7a6a5c0aef1d4ceeb6bac7d1702dd6d6eda73a17d67f5d6f2467d` |
| Caffeine | 164,384 | `67e14ef5c04c193a7fcafa788b55b89a079fd584b202469721ce6d2d6c753090` | 58 / 50 | none | `bf418ab677a31782502229a8fb35bf573f88a36678ec076d6e9337d383e5eae6` |

The Guava POM inherits group/version and license/SCM from `guava-parent`; the exact artifact POM contains no direct license node. The Commons artifact POM inherits group from `commons-parent:81`, declares the exact version and GitBox SCM, and has no direct license node. Caffeine's exact POM directly declares Apache License 2.0 and `scm:git:https://github.com/ben-manes/caffeine.git`.

Immutable revision bindings are Guava `refs/tags/v33.4.8` -> `f06690fa3e874f65515e8fd338a74d636e2c792f`; Commons annotated `refs/tags/rel/commons-collections-4.5.0` -> `7f7fb0244abc940a2e9dd28b67508c0483a58c3e`; Caffeine `refs/tags/v3.2.0` -> `93d845e58d8e7bf2dfc88a31c5a078bca5bf4dbf`. Each root license is exact SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. Source correspondence is 615/615, 359/359, and 50/50 respectively, with zero unmatched or ambiguous entries under frozen module roots.

Caffeine failed at `_license_receipt`, before root append and before the one selector invocation. It was `ARCHIVE_LICENSE_NOT_EMBEDDED`, not `LICENSE_INCOMPATIBLE`. Because the exception aborted acquisition, zero final sources were selected and no production/evaluator run began.

The nine historical false disclosure tokens were `META-INF/LICENSE`, `META-INF/LICENSE.txt`, the canonical Apache hash, four expected docs (`m336_final_semantic_metrics.md`, `m336_final_source_inventory.md`, `m336_final_trust_metrics.md`, `m336_runtime_proof.md`), `evaluation/m336_final_java/role_manifest.json`, and `evaluation/m336_final_java/selector_receipt.json`. They arose from recursive name/string collection, not final-data leakage. The manifest defect was a direct comparison of JSON arrays/lists with `asdict()` tuple-valued structures.

The timed-out node was `tests/test_m29_educational_layer.py::test_chemistry_cli_builds_clean_pack_from_explicit_sources`: the H15 full run stopped at 120 s after 903 passes; its isolated retry passed in 108.85 s. The repaired profile is detailed in the timeout report.

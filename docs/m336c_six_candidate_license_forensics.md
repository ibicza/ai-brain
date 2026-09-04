# M-33.6c six-candidate license forensics

This development repair reuses only the six source candidates disclosed by H17. It performs no new source acquisition. Exact machine-readable inventories, document receipts, raw/canonical hashes, SCM correspondence and first differing spans are in `runs/m336c_development/license_forensics.json` and `candidate_authority.json`.

| Candidate | Historical result | Repaired classification | SPDX/fusion result | Entries |
|---|---|---|---|---:|
| Gson 2.13.2 | REVIEW_REQUIRED | module text remains review; root license exact | Apache-2.0 / REVIEW_REQUIRED | 85/85 |
| HttpCore5 5.3.6 | CONFLICT | OPTIONAL_APPENDIX_OMITTED | Apache-2.0 / VERIFIED_EXTERNAL_CHAIN | 524/524 |
| Jackson Databind 2.20.0 | ELIGIBLE | no historical conflict | Apache-2.0 / VERIFIED_EXTERNAL_CHAIN | 482/482 |
| Log4j API 2.25.2 | CONFLICT | REPLACEABLE_TEXT_DIFFERENCE | Apache-2.0 / VERIFIED_EXTERNAL_CHAIN | 149/149 |
| picocli 4.7.7 | CONFLICT | BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT | Apache-2.0 / VERIFIED_EXTERNAL_CHAIN | 3/3 |
| Reactor Core 3.7.9 | CONFLICT | BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT | Apache-2.0 / VERIFIED_EXTERNAL_CHAIN | 441/441 |

All four historical conflicts are classified, no recognized incompatible project license is present, and all 1,684 Java entries are analysis-eligible. Raw publication remains 0 because the task-supplied authorization grants local analysis, local research, derived knowledge and raw retention, but not raw redistribution.

The 25 discovered license-like documents are role-separated: 9 project licenses, 3 module licenses, 9 NOTICE files, 2 dependency-license files, 1 third-party license and 1 copyright notice. No NOTICE or third-party attribution is fused as the primary project-license channel.

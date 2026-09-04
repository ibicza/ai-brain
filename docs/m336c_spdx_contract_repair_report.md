# M-33.6c SPDX and artifact-contract repair report

## Decision

M-33.6c finishes as **SAFE_CONSERVATIVE_SUBSET** (Outcome B) at exact I18
`4ec1642af9eb6509ec3cbccb998d8faa581c8755`.

The production Java path, candidate-pack replay, independent evaluation, runtime
queries, historic H17 forensics, hypothetical next-stage contract, and both
platform gates all pass. Outcome A is not claimed because the task-supplied
authority permits local analysis and derived/metrics publication but authorizes
zero roots for raw-source publication. No new untouched corpus was acquired.

This repairs roadmap M-33. M-33.6d is the next untouched Java freeze, M-33.7
remains the final four-domain proof, and roadmap M-34 Episodic and Relationship
Memory has not started.

## Graph and frozen reference

The graph-first workflow began at exact E17
`1541805f9cd6c19ff9c372afeefbd41148217736`. The graph changed from 1090 files,
16391 nodes, and 116758 edges to 1090 files, 16389 nodes, and 116748 edges. The
final depth-two E17 comparison found 62 tracked changed files, 268 directly
changed nodes, 207 impacted nodes, and 71 additional affected files.

The production matcher reads the frozen official SPDX License List 3.28.0
snapshot. Its snapshot manifest hash is
`4306f3888f3ccc2b0bac58e984c5eb937be0d6d812a7287a0f3d38a6aac5cce1`;
the frozen license-list-XML commit is
`6f2ddc538acb19180f4c8e96cff94ccf27822e8b`. The snapshot includes Apache-2.0,
MIT, BSD-2-Clause, BSD-3-Clause, GPL-2.0-only, and the matching guidelines.

## Exact-I18 gate result

| Gate | Windows | Karina |
| --- | --- | --- |
| Clean detached exact-I18 checkout | PASS | PASS |
| Ruff format and lint | PASS | PASS |
| Targeted suite | 193 passed | 193 passed |
| Full suite | 1015 passed | 1015 passed |
| No Torch / no network | PASS | PASS |
| Six roots / 120 selected sources | PASS | PASS |
| Selector invocation / rerun | 1 / 0 | 1 / 0 |
| Production / replay / evaluation / runtime | PASS | PASS |
| H17 contract forensics | PASS | PASS |
| Contract mutations rejected | 1008 / 1008 | 1008 / 1008 |
| Wrong trusted facts | 0 | 0 |

Cross-platform comparison passed for all 17 platform-independent outputs with
zero differences. Both platforms produced candidate-pack hash
`43d2db68c29c6ecae131315ae297e969a68543ae47ef3346f487aae404faf674`,
candidate tree hash
`0408f228a25aeb6d936122c598b8790df8984e9124ed4177a0110040dd109c96`,
and sealed production-output hash
`5c6334472d1f50eb6405c36524ccb9dc6951613f41a01fc493a5153d583d5116`.

## License and authority semantics

- The independent license corpus contains 1500 cases. Automatic trust accepted
  504 and was correct for all 504: precision `1.000000`, zero false automatic
  matches, and zero false Apache-2.0 matches.
- All 132 valid optional Apache variants were retained; none was rejected. All
  500 substantive conflict mutations were blocked.
- All four historical license conflicts were classified, with zero false
  candidate conflicts and zero unresolved document roles.
- The 25 discovered license-related documents have explicit roles: 9 project
  licenses, 3 module licenses, 9 notices, 2 dependency licenses, 1 third-party
  license, and 1 copyright notice.
- All six disclosed roots are analysis-eligible and typed; none is raw-source
  publication-eligible. The registry discloses 1684 raw and canonical source
  hashes. Authority axes remain separate, local possession does not imply
  publication authority, and scope changes leave semantic content unchanged.

| Candidate | Historical / repaired license result | Authenticity | Acquisition | Entries: analysis / raw-publication / excluded |
| --- | --- | --- | --- | ---: |
| Gson 2.13.2 | REVIEW_REQUIRED / Apache-2.0 REVIEW_REQUIRED | AUTHENTIC_WITH_SINGLE_CHANNEL | ELIGIBLE_FOR_ANALYSIS | 85 / 0 / 0 |
| HttpCore5 5.3.6 | CONFLICT / OPTIONAL_APPENDIX_OMITTED | AUTHENTIC_WITH_SINGLE_CHANNEL | ELIGIBLE_FOR_ANALYSIS | 524 / 0 / 0 |
| Jackson Databind 2.20.0 | ELIGIBLE / VERIFIED_EXTERNAL_CHAIN | AUTHENTIC_WITH_SINGLE_CHANNEL | ELIGIBLE_FOR_ANALYSIS | 482 / 0 / 0 |
| Log4j API 2.25.2 | CONFLICT / REPLACEABLE_TEXT_DIFFERENCE | AUTHENTIC_WITH_SINGLE_CHANNEL | ELIGIBLE_FOR_ANALYSIS | 149 / 0 / 0 |
| picocli 4.7.7 | CONFLICT / BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT | AUTHENTIC | ELIGIBLE_FOR_ANALYSIS | 3 / 0 / 0 |
| Reactor Core 3.7.9 | CONFLICT / BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT | AUTHENTIC | ELIGIBLE_FOR_ANALYSIS | 441 / 0 / 0 |

Every candidate has the same externally supplied scopes:
`PRIVATE_LOCAL_ANALYSIS`, `LOCAL_RESEARCH_EVALUATION`,
`DERIVED_KNOWLEDGE_ONLY`, and `RAW_SOURCE_RETENTION`. Raw-source and excerpt
publication are ineligible; derived-pack and metrics-only publication are
eligible. All 1684 source entries are analysis-eligible, zero are excluded, and
zero are raw-publication-eligible.

## Java semantic result

The evaluator processed 3519 proposals after the production result was sealed.
Location precision is `1.000000`, location recall `0.982412`, semantic precision
`1.000000`, semantic recall `0.982412`, trust precision `1.000000`, trust coverage
`0.925752`, field-evidence exactness `1.000000`, and resolution agreement
`1.000000`. There are zero wrong-trusted facts, zero post-trust pack failures,
zero production evaluator dependencies, and zero production golden reads.

The installed candidate pack passes exact scoped-descriptor, receiver/method,
constructor, generic-method, throws-declaration, and nested-receiver queries. It
also returns the required ambiguous/not-found outcomes, performs no source or
generated-class execution, invokes no subprocesses, and attempts no sockets.

## Contract closure and readiness

Historic H17 analysis covers 57 paths: zero unknown paths, missing fields,
unexpected fields, unclassified fields, or role mismatches. All 36 formerly extra
protected-field occurrences are classified. The hypothetical next-stage contract
covers 15 artifacts with zero missing/extra protected fields, missing roles,
unknown paths, duplicate paths, or disclosure-claim mismatches.

All 1008 adversarial contract mutations across 14 categories were rejected. The
independently built readiness gate passed all 55 mandatory criteria. Its gate hash
is `0815ddf60edd3bfb32df4ee4f6bdbc38ed7cad5d10a17baca008cdb49af5139f`.
The cross-platform report hash is
`19771257e851d0dee587f112d3026734c6961222ac7d60f2b7c842624677ec47`.

The committed evidence contains reports, logs, hashes, and derived measurements
only. It excludes selected/work-root source trees and all `.java`, `.jar`, and
`.zip` inputs.

No moral, moderation, refusal, political, ideological, personality, or topic
policy was added. M-33.6d should use the metadata-only overprovisioned candidate
pool and a final protocol that accepts sealed local-only inputs without committing
unauthorized source bytes.

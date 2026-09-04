# M-33.6c SPDX and artifact-contract repair report

## Decision

M-33.6c finishes as **SAFE_CONSERVATIVE_SUBSET** (Outcome B) at exact I18
`4ec1642af9eb6509ec3cbccb998d8faa581c8755`.

Both clean detached platform gates pass: Ruff format/lint, 193 targeted tests,
1015 full-suite tests, no-Torch/no-network checks, production, pack replay,
independent evaluation, runtime proof, historic H17 analysis, and the hypothetical
next-stage artifact contract. No new untouched corpus was acquired.

Outcome A is not claimed because all six disclosed candidates are authorized for
local analysis and derived/metrics publication, while zero roots are authorized
for raw-source publication. The final package therefore remains the safe
conservative subset.

This repairs roadmap M-33. M-33.6d is the next untouched Java freeze, M-33.7
remains the final four-domain proof, and roadmap M-34 Episodic and Relationship
Memory has not started.

## Measured result

- Six analysis-eligible roots, 120 selected Java sources, one selector invocation,
  and zero selector reruns.
- 3519 semantic proposals; location and semantic precision `1.000000`, recall
  `0.982412`; trust precision `1.000000`, coverage `0.925752`; zero wrong-trusted
  facts.
- Candidate pack
  `43d2db68c29c6ecae131315ae297e969a68543ae47ef3346f487aae404faf674`,
  tree `0408f228a25aeb6d936122c598b8790df8984e9124ed4177a0110040dd109c96`,
  production output
  `5c6334472d1f50eb6405c36524ccb9dc6951613f41a01fc493a5153d583d5116`.
- Independent license evaluation: 1500 cases, 504/504 correct automatically
  trusted cases, precision `1.000000`, zero false Apache matches, all 132 optional
  variants accepted, and 500/500 substantive conflict mutations blocked.
- Twenty-five license documents have resolved roles; four historical conflicts
  are classified; 1684 raw/canonical source hashes are disclosed.
- Historic H17 and hypothetical next-stage contracts pass with zero unknown,
  missing, extra, unclassified, role-mismatched, or disclosure-mismatched fields.
  All 1008/1008 adversarial artifact-contract mutations are rejected.
- Cross-platform byte comparison: 17 comparisons, zero differences. Independent
  readiness: 55/55 mandatory criteria passed; gate hash
  `0815ddf60edd3bfb32df4ee4f6bdbc38ed7cad5d10a17baca008cdb49af5139f`.

Canonical machine-readable evidence is under `runs/m336c_final_gate/`. Raw selected
sources and `.java`, `.jar`, and `.zip` inputs are intentionally excluded.

The frozen SPDX License List 3.28.0 snapshot manifest is
`4306f3888f3ccc2b0bac58e984c5eb937be0d6d812a7287a0f3d38a6aac5cce1`.
The graph moved from 1090 files / 16391 nodes / 116758 edges at exact E17 to
1090 files / 16389 nodes / 116748 edges before I18.

Candidate authority summary: Gson is `AUTHENTIC_WITH_SINGLE_CHANNEL` with
Apache-2.0 `REVIEW_REQUIRED`; HttpCore5, Jackson Databind, and Log4j API are
`AUTHENTIC_WITH_SINGLE_CHANNEL` with `VERIFIED_EXTERNAL_CHAIN`; picocli and
Reactor Core are `AUTHENTIC` with `VERIFIED_EXTERNAL_CHAIN`. All six are
`ELIGIBLE_FOR_ANALYSIS`. Their analysis/raw-publication/excluded entry counts are
respectively 85/0/0, 524/0/0, 482/0/0, 149/0/0, 3/0/0, and 441/0/0. Derived-pack
and metrics publication are eligible; raw-source and excerpt publication are not.

No moral, moderation, refusal, political, ideological, personality, or topic
policy was added. M-33.6d should use the metadata-only overprovisioned candidate
pool and support sealed local-only inputs without committing unauthorized source
bytes.

# M-33.6f deterministic evaluation artifacts

Evaluation schema v2 separates platform-neutral semantic evidence from platform-specific telemetry. Semantic evidence contains identities, integer counts, decimal ratios, decisions, hashes, normalized categories and readiness. Telemetry contains host identity, platform, timings, peak memory, JDK executable identity and process measurements.

Independent SPDX output is similarly split: the semantic report is rebuilt from counts and rows under `m336f.independent-license-semantic.v1`; compiler/matcher timings and peak Java heap appear only in telemetry. Changing timing leaves the semantic report byte-identical.

The strict registry currently covers all 14 producers and all 41 variants, with zero uncontracted artifacts, contract-only types, ambiguous path contracts or recursive unknown-field acceptance. Read-only inherited evidence remains supported without broadening new contracts.

# M-29.2 trusted educational hardening

M-29.2 keeps `EducationalDerivationGraph` as the single calculation authority and closes trust gaps around runtime currentness, persisted artifacts and learner-facing serialization. It does not add conversational orchestration, progress memory, neural behavior or content policy.

## Trust contracts

- Every `GraphNodeKind` has an explicit operation allowlist. Builders and semantic verification share the same contract; dimension-specific mole and Avogadro relations and unit conversions remain independently recomputed.
- Precompiled explanation, presentation, submission, hint, solution and explicit replay share one live dependency-currentness core. Runtime actions check the bounded entry/session closure before their first write and return a typed exact `EducationalReplayStatus` on failure.
- SQLite checksum/hash/event-chain verification is reported as `STRUCTURALLY_VERIFIED`. `EducationalArtifactAuthorityVerifier`, explicitly injected through `EducationalService`, additionally reconstructs grading, hints, check explanations, solutions, presentations, receipts and session event closures from their authorities.
- Learner-facing methods return immutable public DTOs. Internal graph, receipt, session, provenance, split and event objects remain behind private backend methods; learner text removes graph/source hashes and internal node labels.
- Exercise, graph, grading, hint, explanation, tutor-session, replay, generator, store and catalog schemas are v3. A v2 store/catalog requires an explicit rebuild; it is not silently treated as v3.

## Split and diagnosis truthfulness

Five catalog axes are true content holdouts: formula structure, element combination, numeric range, unit direction and multi-step composition. Two additional axes are honestly named deterministic partitions: template key and language assignment. Every entry records membership in every catalog manifest, and verification requires exact non-overlapping universe coverage.

Misconception evaluation has its own fixture-ID universe and is reported as `SYNTHETIC_CROSS_IMPLEMENTATION`. Fixtures declare their deterministic generator/construction method and `human_review_status=NOT_REVIEWED`. Precision with zero predictions is undefined; reports separate micro precision, macro precision over predicted categories, macro recall, coverage and abstention.

## Verification and performance

`EducationalService.verify()` and CLI `verify` expose both structural and authority results. Service backup verifies both before copying; service restore verifies both after reconstruction. Runtime submit/hint/solution do not call full-store verification.

The M-29.2 acceptance script exercises the prior M-29.1 thresholds, operation mutations, a 10-category by 6-action stale matrix, ten artifact tamper categories, 1,000 public serialization probes, split universes and diagnosis metrics. The benchmark script reports presentation, grading, generic hint, targeted hint, replay/currentness, full service verification and offline catalog compilation separately, while retaining the unchanged 10,000-interaction benchmark for E7 throughput comparison.

No network, torch import, hidden executor, moral/moderation/refusal/political/ideological/topic restriction, M-30 behavior or automatic memory write is added.

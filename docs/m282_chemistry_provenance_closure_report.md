# M-28.2 Chemistry Provenance Closure Report

## Outcome

**Outcome B: chain closed with reviewed manual mappings.** Derived-source identity/content and upstream current state are enforced end to end. CIAAW is deterministic; IUPAC and BIPM use explicit hash-bound human review.

## Versions And Identity

- Domain `1.2.0`, schema `3`
- Source policy / source chain `3.0`; derivation schema `2`
- Knowledge snapshot / result schema `3`
- Sources: 4 official, 1 local policy, 4 derived
- Derivations: 1 deterministic, 2 reviewed manual, 1 policy transformation
- Source-chain hash: `bb23631f47d927d4279d3744b735beec2f246e44c13b223f78d7f526a8dd898f`
- Domain reproducible hash: `0e2fd50177635d1b60c3504bb25fcaccee11a0c158d2b02a59226c4ad0d0011f`

## Integrity Results

- Borrowed/swapped/content mutation attacks: 101 rejected, 0 accepted.
- Upstream transitions: 30 blocked, 0 unsafe uses, 0 ignored official retractions.
- Field evidence: 534/534 production fields covered.
- Acceptance: 2662 cases, `PASS`.
- Dependency minimization prevents RU/BIPM/CIAAW cross-invalidation where unrelated.
- Replay now returns typed derivation, source, upstream, policy, and chain failures.

## Performance

The 10,000-calculation CPU benchmark passed at 144.49 calculations/s; mixed p50/p95/p99 was 6.78/13.61/15.90 ms and peak Python memory was 8,681,154 bytes.

## Limitations

The domain supports 33 selected elements, not unrestricted chemistry. Runtime fetching is forbidden. IUPAC/BIPM reviewed mappings are not described as deterministic. RU naming is local policy, not IUPAC authority data. Conventional atomic weights remain educational values with retained uncertainty.

No moral, moderation, NSFW, refusal, political, ideology, opinion, or personality policy was added. Existing bounded-input, authority, resource, confirmation, and offline-runtime controls remain.

## Recommendation

Proceed to M-29 while retaining the reviewed-manual limitation as an explicit provenance property. A later source refresh may promote IUPAC/BIPM mappings only after a genuinely reliable deterministic official extraction path is available.

Exact H5/E5 hashes, local/Karina pytest counts, reproducibility comparison, and evidence-only diff are appended after both exact-SHA gates.

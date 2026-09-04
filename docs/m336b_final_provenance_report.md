# M-33.6b final provenance report

Status: `BLOCKED` before selection.

The frozen production entry point acquired and qualified all six candidates in
one global network acquisition. Every provenance envelope passed its strict
canonical load/rehash validation, and each SCM receipt binds remote ref
resolution, an immutable 40-hex commit, commit-addressed retrieval, source-tree
identity, license evidence, and source correspondence.

| Candidate | Authenticity mode | Sidecar | Detached signatures | Correspondence | License decision |
| --- | --- | --- | --- | --- | --- |
| Jackson Databind | `SHA256_SIDECAR_VERIFIED` | verified | artifact + POM `PRESENT_UNVERIFIED` | 481 raw exact, 0 canonical-only, 1 unmatched, 0 ambiguous | verified |
| Gson | `SHA256_SIDECAR_VERIFIED` | verified | artifact + POM `PRESENT_UNVERIFIED` | 84 raw exact, 0 canonical-only, 1 unmatched, 0 ambiguous | review required |
| Apache HttpCore5 | `IMMUTABLE_SCM_CONTENT_EQUIVALENCE` | absent | artifact + POM `PRESENT_UNVERIFIED` | 524 raw exact, 0 canonical-only, 0 unmatched, 0 ambiguous | conflict |
| Log4j API | `IMMUTABLE_SCM_CONTENT_EQUIVALENCE` | absent | artifact + POM `PRESENT_UNVERIFIED` | 149 raw exact, 0 canonical-only, 0 unmatched, 0 ambiguous | conflict |
| picocli | `MULTI_CHANNEL_VERIFIED` | verified | artifact + POM `PRESENT_UNVERIFIED` | 2 raw exact, 1 canonical-only, 0 unmatched, 0 ambiguous | conflict |
| Reactor Core | `MULTI_CHANNEL_VERIFIED` | verified | artifact + POM `PRESENT_UNVERIFIED` | 441 raw exact, 0 canonical-only, 0 unmatched, 0 ambiguous | conflict |

Aggregate correspondence: 1,682 eligible entries, 1,681 raw-exact matches,
one canonical-only match, two unmatched entries, and zero ambiguous entries.
All six SCM revision receipts were produced by the real SCM provider. Four
candidates had verified artifact and POM SHA-256 sidecars; two used the frozen
immutable-SCM fallback. Twelve detached signatures were present but unverified,
with zero signature-authority contributions.

Qualification was one-to-one across six candidates: one `ELIGIBLE`, one
`REVIEW_REQUIRED`, four `CONFLICT`, and zero required-candidate failures. The
frozen global minimum is two distinct eligible roots, but the observed count is
one. The selector invocation count is zero and the rerun count is zero, as
required by the stop rule. Production and evaluation invocation counts are
also zero.

All six candidates, including ineligible candidates, were appended to the
disclosed-material registry. The pre-append denylist comparison was zero for
all eleven enforced classes: coordinate, source URL, archive bytes, POM bytes,
raw source, canonical source, source tree, selected-path manifest, declaration
fingerprint, SCM revision, and correspondence.

The sealed bundle independently verified on Windows and Karina with identical
tree hash `52e9f90c4d74dd3b2aa5104afb02917a261c9b1eed49ffb4e8cb8fcf23f8f7a0`,
38 files, six envelopes, and the same ordered envelope-hash list.

Freeze/disclosure assembly is not claimed as a pass. The frozen H17 role
assembler rejects the production script's own root-level
`candidate_qualification_receipts.json` as an unknown role; its classifier also
requires `sealed_acquisition_bundle.json` to be inside the bundle even though
the frozen producer and verifier require that self-excluding manifest outside
the bundle. H17 preserves picocli's observed CRLF POM blob without filters; a
fresh Windows checkout reproduced its exact SHA-256 and passed sealed-bundle
verification. The role-classification defect is post-F17 evidence, not repaired
implementation, and forces Outcome C.

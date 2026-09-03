# M-34.4 oracle-free production trust

The production entry point is
`run_java_acquisition_pipeline(bundle, store, *, deterministic_run_id,
release_identity=None)`. It deliberately has no golden, oracle, expected-label,
expected-payload, confusion-matrix, or hidden-census argument.

`SOURCE_ENTAILED_AND_STRUCTURALLY_VERIFIED` means that exact source bytes and
bundle identity replay; a unique physical declaration and semantic identity
exist; the parser artifacts verify; the declaration is structurally supported;
receiver, parameter, return, bound, and throws types resolve under the frozen
Java 21 universe; accessibility and module exports permit the declaration; no
identity conflict or duplicate physical ancestry exists; every required field
has exactly one policy rule and exact transformation receipt; and no
manual-review-only blocker exists.

The resulting `JavaProductionTrustDecision`, `JavaProductionTrustClosure`, and
`VerifiedJavaProductionAuthorization` contain production identities and
receipts only. They contain no golden ID, expected result, exact-golden-match
flag, or evaluation output hash. Candidate compilation accepts only an
authorization issued by a full production replay. Mechanical approval is
`TRUSTED_PROCESS`; a `USER` approval requires an externally supplied approval
artifact hash.

The sealed production output is created before evaluator access. A file-read
guard rejects oracle, golden, or evaluation paths. Production replay and the
candidate pack are self-contained and remain valid after all evaluation
artifacts are removed. The pack excludes goldens, expected supported labels,
expected payloads, and confusion matrices.

This capability extracts callable/API contract headers. It does not interpret
arbitrary method bodies and does not execute source or generated classes.

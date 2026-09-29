# M-33.6k.13 R38f v3 typed-authorization failure

## Boundary

The preserved v3 attempt reached its Q-like commit and stopped before the F38-like component bundle was created. The preserved route, reservation receipt, repository, and post-failure evidence were inspected without mutation. No acquisition, selector, evaluator, controller route, or reservation operation was run.

The evidence inputs are recorded by semantic role and SHA-256 in `artifacts/m336k13/r38f/v3_typed_authorization_forensics.json`; private and path-bearing values are not published.

## Reconstruction

The prospective `M336K9FinalAuthorization` was reconstructed from the preserved typed-component request, realized legacy authorization input, R38e source, v3 Q-like commit, real profile registry, and the exact component-builder inputs immediately before `build_m336k9_final_authorization` called `M336K5FinalAuthorization.verify`.

The identity tuple resolves uniquely to registered profile `m336k8-rehearsal-v2`, whose status is `REHEARSAL_ONLY`. Its public branch authority is:

`refs/heads/disposable/m336k8-profile-rehearsal-v2`

The v3 request instead used:

`refs/heads/disposable/m336k8-m336k13-r38e-full-rehearsal-v3`

The old outer qualifier accepted that branch because it only checked the generic `disposable/m336k8-` prefix. The typed authorization verifier correctly resolved the registered identity tuple and required exact equality to the profile's `authorization_branch_ref`.

## Predicate result

All 32 reconstructed base, bundle, and profile predicates are recorded in the forensic JSON. Exactly one base predicate fails:

`REGISTERED_PROFILE_BRANCH_REF_EQUALITY`

All other base predicate failures: 0. Bundle mismatches: 0. Profile-binding mismatches: 0. The computed and claimed prospective authorization hashes are equal.

## Authorized repair boundary

R38f may add one pure shared branch-authority predicate and invoke it before any qualifier side effect and from the external pre-reservation preflight. The typed authorization verifier must remain equally strict. No profile value, profile branch ref, identity tuple, official route, policy, pool, reservation, launcher, native dispatch, or final-controller binding may be weakened or changed.

The fresh rehearsal must use the registered exact branch `disposable/m336k8-profile-rehearsal-v2`; the invalid v3 branch is historical evidence only.

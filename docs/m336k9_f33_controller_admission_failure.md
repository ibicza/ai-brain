# M-33.6k.9 F33 controller-admission failure

F33 remains the immutable historical Outcome C at `3c5f64ee32d9d6af7d7810dbeabcc1be9c600771`. Its accepted validate-only receipt is `dd50cc1ae6fb1bc5360b44352092411179f38e216f4342920c3066c00112e39d`; the historical controller was invoked once and completed zero times.

The frozen K8 v1 route tuple was accepted by the typed codecs and by the M336K8 validate-only path. The controller then applied a second independent OFFICIAL-only protocol whitelist containing K5, K6, and K7 but not K8. Its first failing predicate raised `M336K2ProtocolError: M336K5 official protocol run ID is not canonical` before the first route-ledger append.

The failure was reproduced without invoking the historical controller: the frozen F33 identity bundle was loaded through its typed codec and passed directly to the historical side-effect-free controller identity predicate. All route, acquisition, selector, evaluator, candidate, source-body, and vault counters remained zero; no destination or ledger appeared.

The exact classifications are:

- `DUPLICATED_OFFICIAL_IDENTITY_AUTHORITY`
- `CONTROLLER_WHITELIST_OMITTED_TYPED_CANONICAL_IDENTITY`
- `VALIDATE_ONLY_DID_NOT_EXECUTE_CONTROLLER_ADMISSION`
- `DISPOSABLE_PURPOSE_BYPASSED_OFFICIAL_ONLY_CHECK`
- `OFFICIAL_PROFILE_SET_AND_CONTROLLER_SET_DIVERGED`

There are zero unclassified causes. M-33.6k.9 centralizes the identity tuple and status in one profile registry and makes validate-only and the controller call the same side-effect-free admission verifier.

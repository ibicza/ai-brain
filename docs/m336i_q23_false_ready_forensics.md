# M-33.6i Q23 false-ready forensics

Exact baseline: `067855a9c3dfdfd503011444f08896d867beceac`.

The Q23 registry resolves `FINAL_ACQUISITION_PROVIDER` to `refuse_m336h_unfrozen_final_acquisition`. Direct invocation with all five nominal inputs still raises `M336HFinalAcquisitionAuthorizationError: FRESH_FREEZE_AUTHORIZATION_REQUIRED`. The `final` parser exposes only `--output`, so it cannot bind a freeze manifest, authorization, pool, policy, ledger, or vault.

The rebuilt code graph finds `M336HJavaRouteStateMachine` callers only in `tests/test_m336h_native_fresh_java_route.py`; the controller does not use it. The readiness helper validates a supplied receipt and two supplied identities but does not reconstruct the bound registry, manifest, callable sources, rehearsals, quality, ledgers, or staging tree.

Calling `_metrics(None)` in `scripts/m336h_prepare_independent_evaluation.py` returns eight `1.000000` ratios, zero wrong-trusted, zero false automatic SPDX identities, and runtime `PASS`. Selected evaluator mutation cases inspect source text instead of executing a mutated final route.

All seven required blocker classes are recorded in `artifacts/m336i/q23_false_ready_forensics.json`. Phase 0 performed zero final acquisition reservations, zero final acquisition invocations, and received zero final source-body bytes.

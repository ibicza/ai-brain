# M-33.6k.4 identity-flow closure

## Historical flow

The M-33.6k.2 component builder produced acquisition, route-manifest and
route-registry identifiers, but did not produce the external official
`route_run_id`. The disposable coordinator rendered a dedicated template. The
official operator separately created route and stage JSON, the final CLI loaded
their raw strings, the execution plan copied the raw string, and the controller
compared it with `M336K2_FINAL_RUN_ID`. This left two untyped assignment edges:

1. external route JSON -> final CLI -> controller protocol-run parameter;
2. external stage JSON -> execution plan -> native worker state/receipt.

The supplied `m336k2.final-java.route.v1` was route-version-like but was not a
value emitted by any tracked or preserved frozen component. The exact producer
was the untracked official-request construction step. Required unclassified
identity producers: **0**.

## Current flow

`M336K4RouteVersion`, `M336K4ProtocolRunId`, `M336K4AcquisitionRunId`,
`M336K4SelectorRunId`, `M336K4EvaluatorRunId`, `M336K4ExecutionMode`, and
`M336K4RouteComponentId` have distinct immutable codecs, namespace validation,
canonical JSON, schema versions and content hashes. Cross-type equality is
false and cross-type parsing is rejected.

The authoritative flow is:

`typed registry + typed route manifest + one-shot policies -> route identity bundle -> typed authorization -> F29 freeze -> canonical request builder -> exact pre-ledger validator -> internal controller request -> controller/stage/ledger contexts -> H29/E29 identity observations`.

The external `M336K4FinalRouteRequestV2` contains only frozen-object paths,
executable handles, fresh private destinations, exact commit bindings and its
builder/request hashes. It has no route, protocol, acquisition, selector,
evaluator or execution-mode choice. The loader derives all of those values from
the independently verified frozen bundle and authorization.

The side-effect-free validator is the first half of the real command. It uses
the same canonical JSON loader, typed codecs, registry and manifest checks,
freeze and authorization verification, executable/environment checks, a live
exact-capsule Karina host/storage check, destination-set validation and F29
lineage/attestation check. It returns
`FINAL_INVOCATION_ACCEPTED_PRE_LEDGER` and stops before creating any ledger,
vault, source request, selector reservation or evaluator reservation.

The controller, route ledger, acquisition ledger, selector ledger, evaluator
ledger, H29 receipt and E29 receipt are seven independent observers of the
same frozen bundle. The three one-shot ledgers bind the bundle in their context
or reservation hash; the public acquisition and H29/E29 observations also
carry the type-correct canonical identities. A mismatch is rejected before the
corresponding reservation.

The disposable FINAL path also executes a 25-case mutation matrix after its
F-like freeze and before controller invocation. Twenty-one invalid cases pass
through the real builder, loader, typed preflight, controller-stage guard or
ledger-identity guard; four additional cases prove the valid exact pre-ledger
path creates no ledger, vault, source GET, selector reservation or evaluator
reservation. Readiness requires accepted invalid cases 0 and wrong rejection
layers 0.

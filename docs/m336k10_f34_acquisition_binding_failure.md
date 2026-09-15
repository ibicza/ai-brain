# M-33.6k.10 F34 acquisition-binding failure

F34 (`12f590937fdb3e402a92b25b215e0476ef30a20a`) is an immutable historical `OUTCOME C - BLOCKED`. Its parent is exact Q34 (`0478f3b2c1401812a4786d7c6d04e91cb8ae4f7d`), whose parent is exact R34 (`2defe196857721a5f1859cb183bd4c1eed20d0f4`). H34 and E34 were never created.

## Reproduced failure

The side-effect-free F34 acquisition-input verifier was run against the exact committed F34 candidate pool, policy, authorization, authority statement, disclosure registry, and historical F34 code. It produced the original error:

`M336K2ProtocolError: M336K2 acquisition inputs are inconsistent`

The reproduction created zero route events, acquisition events, candidate attempts, terminal receipts, vault files, or source-body bytes.

## Exact inconsistency

The official metadata-only pool contains 96 candidates from 64 organizations, with at most two candidates per organization. Its semantic hash is `b48ee354dc710a6c0ac0ed2cfceb1385c0d12cc8efb6b8fbef00e8d2f6ab572e`; its bytes hash is `78cfb85fc59687186f0e420d410bf648816bce6ae2539acb445f8da74d77a0fa`.

The frozen F34 acquisition policy instead binds the disposable pool hash `b4128991cdaa118ddac58bb3e87f060028b5794374e75b2b68dca1a8f59cd40e` and the single host `fixture.invalid`. The frozen authorization binds the official pool hash but reuses that disposable policy hash and host. The exact official pool requires the derived host tuple `codeload.github.com`, `github.com`, and `repo.maven.apache.org`.

The builder therefore replaced the pool without rebuilding every dependent acquisition identity. The validate-only path did not evaluate that semantic graph, and the controller appended `ACQUISITION_RESERVED` and `ACQUISITION_STARTED` before the worker discovered the mismatch. The historical route ledger contains six events and ends in `FINAL_ROUTE_FAILED`; all acquisition, selector, and evaluator ledgers are absent.

## Exhaustive root-cause map

1. `OFFICIAL_POOL_REPLACED_WITHOUT_POLICY_REBUILD`
2. `DISPOSABLE_ACQUISITION_POLICY_REUSED_BY_OFFICIAL_FREEZE`
3. `OFFICIAL_AUTHORIZATION_MIXED_NEW_POOL_WITH_LEGACY_HOSTS`
4. `NETWORK_AUTHORITY_NOT_DERIVED_FROM_OFFICIAL_POOL`
5. `VALIDATE_ONLY_OMITTED_ACQUISITION_INPUT_SEMANTICS`
6. `ROUTE_EVENTS_APPENDED_BEFORE_ACQUISITION_INPUT_ADMISSION`

Unclassified root causes: 0.

## R35 design boundary

The v3 graph is a one-way typed hash graph:

`exact candidate pool -> pool binding -> derived network authority -> official policy -> final authorization -> ledger/stage bindings -> acquisition-binding receipt`

Official network hosts are derived from every pool URL that a provider may dereference; callers cannot provide an official host tuple. The official policy and authorization are built from the same typed pool, network, profile, provider, and shared-policy objects. Rehearsal policy and provider construction remain on a separate builder path.

Validate-only recomputes the complete acquisition binding and places its receipt hash in the preledger receipt. The controller recomputes the same binding and requires byte-equivalent receipt identity before appending its first route event. The worker repeats the checks only as defense in depth. A semantic pool/policy/authorization/provider mismatch therefore produces zero route and acquisition events.

The persistent capsule is a historical frozen input and is neither recreated nor retargeted by R35.

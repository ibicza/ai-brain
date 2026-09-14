# M-33.6k.9 graph-first identity authority review

The code-review graph was rebuilt at exact F33 before broad source inspection. It identifies `run_m336k5_final_controller` as the shared controller reached by the K5, K7, and K8 final-route entry points, and `_verify_final_identity` as the controller-only identity predicate executed before the first ledger append.

## Independent executable identity authorities before repair

1. `m336k5_identity.py`: typed constants and five separately maintained `official_values` sets.
2. `m336k5_request.py`: an independent K5/K6 purpose-to-protocol set.
3. `m336k7_request.py`: an independent exact K7 OFFICIAL protocol predicate.
4. `m336k8_request.py`: an independent exact K8 OFFICIAL protocol predicate.
5. `m336k5_controller.py`: an independent K5/K6/K7 controller whitelist.
6. `m336k5_authorization.py`: an independent protocol-to-branch map.
7. `m336k5_registry.py`: an independent namespace-to-route-version switch.

All seven authorities are classified. Unclassified identity authorities: zero.

## Producers and consumers

The typed identity builders produce route version, protocol, acquisition, selector, evaluator, and execution-mode values. The route/request builders bind them into the identity bundle and authorization. Validate-only consumes the bundle, authorization, freeze, route registry, stage identity policies, destination set, and platform preflights. The final controller consumes the validated bundle and preledger receipt before the route ledger. The acquisition, selector, and evaluator ledgers consume their respective IDs from the same bundle through the private stage adapter. H and E publication consume the route/freeze identities and final authorization through the stage request and publication contracts.

The repaired route replaces the seven manual acceptance lists with one canonical route-profile registry. Compatibility constants remain aliases for historical readers, not independent authorities.

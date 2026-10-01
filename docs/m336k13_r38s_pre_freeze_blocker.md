# M-33.6k.13 R38s pre-freeze blocker

Outcome: `PRE_FREEZE_BLOCKED`.

The original `M336K12 live plan binding changed` failure was reproduced without official side effects and was repaired locally with a strict canonical v6-to-v5 projection. The unchanged complete v5 verifier accepts only that exact projection, and the returned active parity is rebound to the v6 plan-binding hash. The direct verifier suite passes 19 tests.

The real official v6 component-builder entrypoint was then exercised in a fresh temporary Git repository with independent private and staging roots, a fresh exact write-once plan, lifecycle receipt, plan-binding receipt, and complete request. The old partial Phase-23 staging was not copied or admitted.

That run passed the repaired native-stage verifier and the full v6 freeze assembler. It then failed at the typed compatibility gate with `M336K8 compatibility gate V2 is invalid`. The v6 plan has 35 components and the gate includes three generated compatibility artifacts, so its exact consumed-artifact count is 38. `M336K8FrozenContractCompatibilityGateV2.verify` permits only the historical counts 24, 29, and 33.

Repairing this terminal pre-freeze blocker requires a bounded source change in `src/ai_brain/stage3/acquisition/m336k8_contracts.py` to declare and verify the v6 consumed-component closure. That file is outside the authorized R38s source scope. Faking count 33, omitting v6 artifacts, catching the typed failure, or weakening the gate would violate the task contract.

No Q38S, generation-2 root or reservation, or F38 was created. No official controller, acquisition, selector, evaluator, reservation release, validate-only operation, official ledger write, or vault write occurred.

The exact next operation requires separate authorization: permit a bounded v6 compatibility-gate source repair in `m336k8_contracts.py`, with direct count/round-trip/mutation tests, and then resume R38s from Q38R without reusing the preserved partial staging.

## Resolution in the authorized retry

The user separately authorized that bounded repair and a new iteration. The canonical compatibility layer now recognizes the exact 38-artifact v6 closure and selects the typed v6 final-controller bootstrap producer while preserving historical behavior. Direct count, round-trip and fully-rehashed producer-mutation tests pass, and the real official v6 component-builder E2E completes from a fresh temporary repository and staging root. This section records the later resolution without altering the historical `PRE_FREEZE_BLOCKED` evidence above.

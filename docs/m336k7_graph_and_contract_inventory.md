# M-33.6k.7 graph-first producer/consumer inventory

The refreshed project graph contains the M336K5 request, controller, freeze, resource, and M336K6 persistent-capsule paths. Concrete source inspection was used where the graph did not index dataclass field consumers.

| Semantic role | Producer | Producer schema/output | Freeze component | Current consumer | Cross-binding |
| --- | --- | --- | --- | --- | --- |
| resource policy | `M336K7ResourceBudgetPolicy.build` | strict phase-neutral dataclass | `resource_budget_policy` | `M336K7ResourceBudgetPolicy.from_dict` | authorization, input bundle, resource gate |
| resource observation | `M336K7ResourceObservationReceipt.from_m336k6_aggregate` or `.from_samples` | strict measured-only dataclass | `resource_observation` | `M336K7ResourceObservationReceipt.from_dict` | input bundle, resource gate |
| storage reservation | existing real allocator/receipt | strict `M336K5StorageReservationReceipt` | `storage_reservation` | `storage_reservation_from_dict` | policy size, filesystem identity, content and allocation |
| resource gate | `M336K7ResourceGateReceipt.build` | strict independent comparisons | `resource_gate` | `M336K7ResourceGateReceipt.from_dict` plus rebuild | policy, observation, reservation, filesystem |
| persistent capsule | M336K6 persistent preparer | strict private capsule | private handle | `M336K6PrivateExecutionCapsule.from_dict` | canonical binding set, including its historical implementation tip |
| persistent public receipt | M336K6 capsule producer | strict public receipt | `persistent_capsule_receipt` | V3 exact-field consumer | canonical binding set |
| legacy public receipt | unchanged SSH capsule producer | strict legacy receipt | hash-bound, private handle | legacy typed loader | compatibility receipt and binding set |
| Python environment | unchanged capsule/startup producer | hashed manifest | `python_environment_manifest` plus private handle | V3 exact hash consumer | compatibility receipt and binding set |
| executable dependencies | Windows and Karina executable producers | strict hashed manifests | `executable_dependency_manifest`; private Karina handle | typed dependency loaders | authorization, compatibility receipt, binding set |
| startup policy | M336K5 startup policy builder | strict dataclass | `python_startup_policy` | strict startup policy loader | authorization, input bundle, binding set |
| liveness | `verify_m336k6_persistent_capsule` | strict liveness dataclass | `capsule_liveness` | V3 exact-field consumer | binding set and live preflight |
| preservation | M336K6 preservation planner | hashed public receipt | `preservation_set` | V3 hashed consumer | binding set |
| cleanup cutoff | M336K6 cleanup controller | hashed public receipt | `cleanup_cutoff_state` | V3 hashed consumer | binding set and post-freeze mutation guard |
| F32 freeze | `materialize_m336k7_f32` | strict F32 manifest | `freeze_manifest.json` | `M336K7FreezeManifest.from_dict` | exact Q32, implementation, bundle, authorization, component bytes |
| final request | `build_m336k7_final_route_request` | strict V3 request | external private request | `load_m336k7_final_route_request` | exact committed F32 inputs and private handles |

All current post-freeze public inputs are passed through the compatibility gate with exact field-set, semantic-role, canonical byte roundtrip, and hash checks. The F32 route does not call the historical M336K5 resource lookup or historical capsule/freeze comparison. Producer without typed output schema: 0. Consumer without typed input schema: 0. Unclassified frozen components: 0.

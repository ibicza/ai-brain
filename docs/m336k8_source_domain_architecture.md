# M-33.6k.8 source-domain architecture

M-33.6k.8 separates the current Windows controller from the preserved Karina runtime capsule. Their complete project-source identities are allowed to differ. Only the explicitly enumerated bridge surface must remain byte-identical and schema-compatible.

| Source domain | Authoritative content | Producer commit role |
| --- | --- | --- |
| `CURRENT_IMPLEMENTATION_CONTROLLER` | current source identity, controller environment and dependencies, startup binding, route identity, authorization | final R33 implementation tip |
| `PERSISTENT_KARINA_RUNTIME_CAPSULE` | preserved capsule environment, dependencies, content, liveness and source wrapper | immutable capsule plus a wrapper built at R33 |
| `CROSS_DOMAIN_BRIDGE` | seven byte-equal executable/schema files, compatibility, assembly and legacy-alias receipts | final R33 implementation tip |
| `PHASE_NEUTRAL_SHARED_POLICY` | resource policy, observation, reservation and gate | frozen historical policy inputs |
| `HISTORICAL_READ_ONLY` | F31/F32 failure forensics only | historical commits |

`M336K8ProjectSourceIdentityPolicy` hashes Git-object and live rows for tracked `src`, `scripts`, `tools`, `schemas`, `pyproject.toml`, and `uv.lock` content in UTF-8 repository-relative byte order. A controller receipt passes only when committed and live rows, path sets, and the clean source-scoped checkout agree.

`M336K8FreezeAssemblyPlan` is the single semantic producer-origin map for disposable and official freezes. `M336K8FreezeInputAssembler` consumes exactly its 21 typed inputs. The generic environment and dependency names exist only as byte-identical private aliases for unchanged native workers, proven by `M336K8LegacyControllerAliasReceipt`.

The phase-neutral V4 request loads exact committed freeze bytes, recomputes current source identity, assembly, semantic compatibility, resource and capsule bindings, and returns `FINAL_INVOCATION_ACCEPTED_PRE_LEDGER` with zero route side effects. It does not call the historical K7 validator. Reservation release and controller invocation require that accepted receipt and occur only in the execution path.

Compatibility gate V2 covers all 24 post-freeze artifacts, executes a semantic verifier for every artifact, and fails on missing or unused consumers, schema or byte-roundtrip changes, producer-origin differences, phase-specific public fields, default lookups, direct full-identity equality, or semantic binding mismatches. The 44-case closed-under-rehash suite recomputes mutated hashes and requires rejection at the declared semantic layer rather than at an outer hash.

After F33, frozen inputs and the persistent capsule are immutable. Cleanup, capsule recreation, regenerated frozen components, acquisition before accepted validation, selector invocation before controller completion, and evaluator invocation before H33 remain forbidden.

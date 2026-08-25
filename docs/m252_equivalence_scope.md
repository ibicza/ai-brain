# M-25.2 Equivalence Scope

## Definitions

`FULL_EXECUTION_TRACE` is the trusted default. Two skills are interchangeable
only when the requested and selected `ProgramSpecification` hashes are equal.
This preserves final state, ordered actions, intermediate states,
`action_stream_hash`, and exact audit behavior.

`FINAL_STATE_ONLY` permits an explicitly reviewed structural substitution when
the installed candidate belongs to the same verified final-state effect class.
It does not claim trace, intermediate-state, observer, or future side-effect
equivalence.

## Search Policy

| Installed evidence | Scope | Status | Exact | Next action |
|---|---|---|---:|---|
| Exact structural member | Either | `EXACT_MATCH` | true | `SELECT_EXACT` |
| Final-state class only | `FULL_EXECUTION_TRACE` | `NO_MATCH` | false | `RUN_SYNTHESIS` |
| Final-state class only | `FINAL_STATE_ONLY` | `FINAL_STATE_EQUIVALENT` | false | `REVIEW_EQUIVALENT_CANDIDATES` |
| Order-sensitive non-exact class | Either | `NO_MATCH` | false | `RUN_SYNTHESIS` |

An installed exact member always wins, even when another class member has a
smaller skill ID. A final-state result exposes every active class member and a
deterministic canonical representative, but no member is labelled exact.

## Bound Artifacts

`EquivalenceScope` is included in `SkillQuery`, `SkillSearchResult`,
`SkillSelectionReceipt`, `SkillDispatchReceipt`, every artifact hash, and
Stage-2 audit evidence.

Equivalent selection additionally binds:

- requested and selected structural hashes;
- final-state effect hash;
- current equivalence-class hash and membership;
- `structural_identity_differs=true`;
- `full_trace_equivalent=false`;
- search status and special confirmation decision.

Changing any bound value invalidates the receipt hash or fails policy
revalidation.

## Confirmation

`CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION` is mandatory for equivalent-only
dispatch. Ordinary `CONFIRM_SELECTION` is rejected. Confirmer identity and type
remain mandatory, and the candidate warning states that action order,
intermediate states, and `action_stream_hash` may differ.

# M-25.2 Final-State Equivalence Safety Report

## Decision

**OUTCOME A: semantic route safely hardened.**

Structural routing remains exact. Final-state equivalence is explicit,
scope-bound, non-exact, warning-bearing, review-only, specially confirmed, and
fully revalidated before dispatch.

## Implemented

- Stage-2 and SkillRegistry schema v3.
- `FULL_EXECUTION_TRACE` trusted default and explicit `FINAL_STATE_ONLY` scope.
- Exact structural member always preferred.
- Honest final-state effect terminology and persisted hashes.
- Requested/selected structural binding in search, selection, dispatch, hashes,
  and audit events.
- Dedicated `FINAL_STATE_EQUIVALENT` status and review action.
- Dedicated equivalent-selection confirmation mode.
- Current class and membership revalidation at dispatch.
- Trace/intermediate-state property validation without modifying Stage 1.
- Explicit v2 rebuild policy.
- Learned authority remains zero.

## Acceptance Results

| Gate | Result |
|---|---:|
| Exact scope matrix | 178 / 178 |
| Structurally different candidate returned as exact | 0 |
| Controlled RU/EN retrieval | 356 / 356 |
| Cross-language equality | 1.0000 |
| Structural full dispatch | 89 / 89 |
| Final-state property executions | 640 |
| Final-state class mismatches | 0 |
| Trace-distinct classes identified | 16 / 16 |
| Full-trace substitutions | 0 |
| Equivalent substitutions without special confirmation | 0 |
| Order-sensitive substitutions | 0 |
| Unsafe automatic selections | 0 |
| Learned semantic authority | 0 |

## Quality Checks

- Full local pytest: `509 passed`.
- M-25 deterministic acceptance: required before final freeze.
- M-25.1 fair acceptance: required without blind reopen or retraining.
- M-25.2 semantic-route acceptance: PASS in development validation.
- Complete ruff and exact-SHA Karina evidence are recorded by the final gate.

## Preservation

Stage-1 interpreter, RuleMemory, bounded execution, installed rules, registers,
primitives, learned trust policy, historical M-25/M-25.1 artifacts, and release
tags remain unchanged. The `gpt` branch is not modified.

M-25.2 may proceed to M-26 factual memory after the exact-SHA local and Karina
gates remain green.

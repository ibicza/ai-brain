# M-27.1 Unified Response Lifecycle

`UnifiedResponseEnvelope` schema v2 has three stages. Read-only factual answers
are `COMPLETED`. Skill selections and tool proposals are `PREPARED`. Confirmed
execution creates a new `COMPLETED` response; rejection or trusted execution
failure creates `FAILED` with a typed failure hash and no success authority.

Final responses bind request, route, prepared parent, confirmation,
selection/proposal, dispatch/result, Stage-1 execution where applicable,
complete dependency snapshot, timestamps, stage and schema. The envelope
enforces one authority domain. Composite and failed responses cannot carry
successful payloads.

Production methods are `dispatch_skill_and_respond` and
`execute_tool_and_respond`. The CLI persists and returns their final envelope;
lower-level dispatch/execution remains available for compatibility.


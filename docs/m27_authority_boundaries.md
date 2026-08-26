# M-27 Authority Boundaries

| Source artifact | Permitted authority | Forbidden authority |
|---|---|---|
| `FactAnswerBundle` | Informational fact answer | Skill/tool execution, fact write |
| `SkillSelectionReceipt` | Reviewable skill candidate | Fact approval, tool call |
| `SkillDispatchReceipt` | One confirmed bounded Stage-1 execution | Fact write, tool invocation |
| `ToolCallProposal` | Reviewable local arguments | Execution before confirmation |
| `ToolResultBundle` | Informational local result | Fact approval, skill dispatch, rule install |
| Assistive route | Ranked review candidates | Exact route, answer, execution, memory write |

`UnifiedResponseEnvelope` enforces at most one authority-bearing payload. Composite requests contain none. The service has no API that converts a skill or tool result into a fact proposal. Cross-domain requests are rejected and audited as `CROSS_AUTHORITY_ACTION_REJECTED`.

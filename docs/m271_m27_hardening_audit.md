# M-27.1 M-27 Hardening Audit

Baseline: implementation `8503d12392996e96159a61a76aa524f5a4070b47`,
evidence HEAD `a85fe24a28f6c40025a4c228dfeb07f96759794b`.

## Findings

1. `UnifiedRouterService.replay` in
   `src/ai_brain/stage2/router/service.py` compares only the stored
   `fact_memory_hash` with the current FactMemory snapshot. SkillRegistry,
   RuleMemory, ToolRegistry, implementation and policy dependencies are ignored.
2. `ToolRegistry.default` in `src/ai_brain/stage2/router/tool_registry.py`
   hashes the entry function source and textual input contract only. Helper
   functions, constants, parsing, Decimal context and rendering policy are not
   bound.
3. `decimal_arithmetic` and `_decimal` in
   `src/ai_brain/stage2/router/tools.py` accept values through `str()`, do not
   bound exponents, and call `format(result, "f")` before proving bounded output.
4. `FactMemory._resolution_evidence_links` in
   `src/ai_brain/stage2/facts/memory.py` rejects incomplete removed-side evidence
   only when retained-side support is also absent. Winner support can therefore
   remove unrelated competitors.
5. `FactMemory._resolve_conflicts_for_claim_event` accepts
   `selected_claim_ids` supplied by supersession without requiring membership in
   each affected ConflictGroup.
6. `validate_request` in `src/ai_brain/stage2/router/request.py` verifies the
   envelope and original-input hashes but does not recompute
   `semantic_input_hash` or strictly validate all typed fields.
7. `ExactUnifiedRouter._structured` validates a structured tool request as an
   existing tool ID plus an arguments object. Exact authority is granted before
   per-tool argument and resource validation.
8. `UnifiedRouterService.dispatch_skill` and `execute_tool` return raw execution
   artifacts. There is no final `UnifiedResponseEnvelope` completing the
   prepared response lifecycle.
9. The audited baseline uses RouterStore schema v1 and FactMemory schema v3.
10. M-27 exact-SHA evidence is in `runs/m27_final_gate`; local and Karina gates
    passed at implementation SHA `8503d12392996e96159a61a76aa524f5a4070b47`.

## Hardening Decision

M-27.1 uses RouterStore/Router/Tool/Response schema v2 and FactMemory schema v4.
Legacy artifacts remain inspectable through explicit non-destructive migrations,
but incomplete dependency bindings and unsafe v3 conflict resolutions are never
promoted to current trusted state.

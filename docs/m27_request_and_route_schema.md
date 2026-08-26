# M-27 Request and Route Schema

`RequestEnvelope` binds source kind, original input, structured payload, language, requested temporal points, requested equivalence scope, and schema version. IDs are unique per request; `original_input_hash` and `semantic_input_hash` remain stable for identical content. Request IDs are never inserted into parser-visible text.

Targets are `FACT_QUERY`, `SKILL_REQUEST`, `TOOL_REQUEST`, `CLARIFICATION`, `UNSUPPORTED`, and `COMPOSITE_REQUIRED`. Authorities are `EXACT_STRUCTURED`, `EXACT_CONTROLLED`, and review-only `ASSISTIVE_PROPOSAL`.

`RouteDecision` binds parser evidence, candidates, ambiguity fields, next action, and all dependency snapshots. `RouteReceipt` additionally binds the chosen target and confirmer identity where confirmation is required. Reusing a receipt with another request or changing its target invalidates the hash.

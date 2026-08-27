# M-28 Chemistry Domain Architecture

The package `ai_brain.stage2.domains.chemistry` is a bounded client of the frozen Stage-2 infrastructure.

```text
RU/EN controlled request
  -> ChemistryUnifiedRouter
  -> FACT_QUERY or TOOL_REQUEST
  -> FactMemory query or PREPARED ToolCallProposal
  -> explicit ToolCallConfirmation
  -> knowledge-bound Decimal calculation
  -> ToolResultBundle + ChemistryResultBundle
  -> content-addressed result store and deterministic renderer
```

Facts retain FactMemory authority. Calculations retain Tool authority. A calculated value cannot approve a claim, resolve a conflict, or write FactMemory. Formula parsing and all tools are local, deterministic, CPU-only, network-free, and torch-free.

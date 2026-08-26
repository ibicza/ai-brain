# M-27 Unified Router Architecture

The trusted router is a CPU-only layer above the frozen Stage-1 executor, SkillRegistry v3, and FactMemory v3. One `RequestEnvelope` produces one `RouteDecision` in exactly one authority domain.

```mermaid
flowchart LR
  R[RequestEnvelope] --> X[Exact structured or controlled parsers]
  R --> A[Assistive research proposal]
  X --> F[FactMemory read]
  X --> S[Skill selection and confirmation]
  X --> T[Tool proposal and confirmation]
  F --> U[UnifiedResponseEnvelope]
  S --> U
  T --> U
  A --> V[Manual route review only]
```

Trusted code lives in `ai_brain.stage2.router`. Research code lives in `ai_brain.stage2.router_research` and is not imported by the trusted package. Route decisions bind FactMemory, SkillRegistry, RuleMemory, ToolRegistry, Stage-1, and Stage-2 versions and hashes. A changed dependency invalidates confirmation or execution.

The precedence policy is explicit: a structured source kind validates only its declared schema; controlled parsers run independently; multiple complete parses clarify; one typed missing field clarifies; no complete parse is unsupported. Assistive text never creates exact authority.

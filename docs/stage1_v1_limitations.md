# Stage-1 v1 Limitations

- Exactly four registers, `R0-R3`, represent non-negative integer counts.
- Exactly three primitives and six controlled semantic families are supported.
- RU/EN controlled language is finite and programmed, not unrestricted natural language.
- Neural frontends remain research-only and outside the trusted package.
- Generic CEGIS has a finite candidate budget.
- Property verification is scoped to the current DSL and specification semantics.
- Execution limits are intentionally conservative and reject larger trusted workloads.
- RuleMemory and audit are single-host, file-based persistence.
- Atomic replacement and directory durability depend on filesystem guarantees; directory `fsync` may be unavailable on Windows.
- The audit hash chain cannot prove that its tail was not deleted without an external anchor.

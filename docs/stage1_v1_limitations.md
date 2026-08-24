# Stage-1 v1 Limitations

- The language frontend is controlled RU/EN, not unrestricted natural language.
- Its vocabulary is the frozen train plus extended production vocabulary audited in M-23.1.
- There are four non-negative integer registers and three exact primitives.
- The six known families are intentionally narrow.
- Clarification is bounded to one typed round.
- Generic CEGIS is budgeted and safely abstains when it cannot verify a candidate.
- Rule execution is deterministic and can take a number of primitive steps proportional to register contents.
- Neural language-to-spec models remain research-only and are excluded from the trusted package.
- Stage-1 v1 does not learn new primitives or change its own grammar at runtime.

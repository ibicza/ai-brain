# M-27 Fact / Skill / Tool Separation

Facts, skills, and tools remain separate stores and object models. The router stores references to their snapshots and hashes, not copies of their content.

- Fact reads may answer without execution confirmation and preserve `CONFLICT`/`NO_FACT` exactly.
- Skill routes reuse exact structural retrieval and the existing explicit confirmation semantics. `FULL_EXECUTION_TRACE` remains the default.
- Tool routes prepare typed proposals and execute only after a matching confirmation.

No fallback crosses domains: `NO_FACT` does not trigger a tool or skill; a tool output is not committed as a fact; a skill output is not knowledge; a fact answer is not an executable argument.

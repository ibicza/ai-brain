# M-28 Formula Parser Security

The parser is bounded recursive descent, not `eval`, a Python expression, or a recursive regular expression. It uses one forward cursor, exact ASCII case, complete consumption, bounded depth/counts, and typed errors with positions.

Resource checks occur before unbounded allocation. Expansion checks multiplication and aggregate atom limits. Renderer roundtrip preserves composition and AST semantics. The acceptance battery rejects 130 malformed/pathological formulas.

# Stage-1 Acquisition v1 Freeze

Stage-1 rule acquisition is frozen at commit `11b573e` and annotated tag
`stage1-acquisition-v1`.

## Supported Backend

- typed `ProgramAst`, clauses, predicates, actions, and bindings;
- generic target-independent grammar and CEGIS search;
- static, abstract, property, and exact-execution verification;
- exact external register state and interpreter;
- `RuleMemory` with evidence-backed write policy;
- primitives `MOVE_ONE`, `DROP_ONE`, and `HALT`;
- statuses `FORMALLY_VERIFIED`, `PROPERTY_VERIFIED`,
  `IDENTIFIED_IN_HYPOTHESIS_SPACE`, `CONSISTENT_WITH_DEMONSTRATIONS`,
  `PROVISIONAL`, `AMBIGUOUS`, `REJECTED`, `UNSUPPORTED`, and
  `SEARCH_BUDGET_EXHAUSTED`.

`RuleMemory` accepts a property-verified rule only with a non-empty full
`ProgramSpecification` and accepted property-verifier evidence. Demonstration-only,
ambiguous, rejected, unsupported, and provisional results are not trusted writes.

## Validation Result

M-22.3a ended in conservative `OUTCOME B`. Hidden semantic correctness and
property acquisition were perfect in the black-box run, and the independent
mutation verifier produced zero false accepts on 10,000 known-incorrect mutations.
The benchmark nevertheless contains only six black-box-validated specification
families, so it does not establish broad algorithm acquisition.

## M-23 Boundary

M-23 may add a controlled Russian/English language frontend that proposes a
canonical `ProgramSpecification`, validates it, asks one bounded clarification,
and requires trusted approval before invoking the frozen acquisition and memory
path.

M-23 may not redesign the DSL, CEGIS, verifier, interpreter, external state, or
approval semantics. Language models may not emit trusted ASTs, execute rules,
mark proposals verified, inspect hidden evaluator state, or write to `RuleMemory`
without `PROPERTY_VERIFIED` evidence and explicit approval.

# Stage-1 v1 Program Specification

`ProgramSpecification` schema version 1 contains `inputs`, `outputs`, ordered `transfers`, `drops`, `preserve`, `terminate_when_empty`, `allowed_variables`, `allowed_primitives`, ordered `phase_constraints`, and `unsupported`.

All fields are mandatory in trusted form/JSON input. Variables are restricted to `A`, `B`, `C`, and `D`. Primitives are restricted to `MOVE_ONE`, `DROP_ONE`, and `HALT`. A source cannot equal its destination. Changed roles cannot also be preserved. Phase actions must exactly match drops and transfers, and every consumed source must occur in the termination condition.

Canonical DSL consists of deterministic clauses followed by a binding line. Example:

```text
NE A M A C
E A NE B M B C
E A E B H
A R0 B R1 C R2 D R3
```

Canonical DSL acquisition requires a separate complete specification and is property-verified before approval.

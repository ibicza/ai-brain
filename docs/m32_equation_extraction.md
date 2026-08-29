# Equation and quantity extraction

Structured quantity declarations compile to exact dimension vectors and optional units. Equation declarations compile to a bounded AST, typed variable bindings, explicit applicability, and required capability IDs.

The kinematics source sentence for constant acceleration produces `v = v0 + a*t` with velocity, acceleration, and time dimensions. The generic scalar solver isolates one unknown using `Fraction`, rejects nonlinear/ambiguous/zero-divisor cases as `NEEDS_NEW_CAPABILITY`, and never silently approximates.

The held-out set repeats 125 independently enumerated exact tasks; all solve to the reviewed expected value and dimension using the compiled rule.

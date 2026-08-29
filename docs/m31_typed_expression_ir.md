# Typed expression and procedure IR

The bounded AST supports variables, constants, addition, subtraction,
multiplication, division, integer power (-12 through 12), equality, inequality,
boolean conjunction/disjunction, and explicit capability references. Operators
have fixed arity and depth is bounded. Variables declare type, unit/dimension,
domain role, range, and optional semantic entity role.

There is no `eval`, Python source, or dynamic code. Injection-like source text is
rejected inside executable expressions. Rules carry preconditions,
postconditions, scope, assumptions, exclusions, exceptions, validity interval,
required capabilities, and unsupported cases. Procedure step graphs can read a
fact, invoke a capability, apply a verified rule, validate, branch, and emit a
typed result; cycles, unreachable steps, and unbound authority fail closed.

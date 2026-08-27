# Chemistry Numeric Safety

Chemistry and generic router arithmetic use `trusted_decimal.parse_bounded_decimal`.
It accepts strings and integers only; bool, float, arbitrary objects, malformed
syntax, oversized coefficients, extreme scales/exponents, and overlong raw input
are rejected before arithmetic or rendering.

Limits include 512 raw/rendered characters, 128 coefficient/result digits,
absolute and adjusted exponent 256, context precision 120, and absolute quantity
below `1e100`. Integer conversion is bounded before allocation.

Rendering performs a preflight size check and never invokes user-defined
`__str__`. The 84-case attack battery reports zero allocation bypasses, zero
float/bool acceptance, and zero malformed exact routes.

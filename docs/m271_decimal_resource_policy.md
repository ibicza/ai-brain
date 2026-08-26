# M-27.1 Decimal Resource Policy

Trusted operands are canonical decimal strings, integers excluding `bool`, or
`Decimal` through the Python API. Floats, bytes, containers, arbitrary objects,
NaN/infinities, locale forms and malformed text are rejected before conversion.
Integer `bit_length` and raw text length are bounded before `str()`/`Decimal()`.

Default immutable limits:

| Limit | Value |
| --- | ---: |
| operands | 16 |
| raw operand characters | 512 |
| coefficient digits | 128 |
| absolute exponent | 256 |
| scale | 256 |
| adjusted exponent | 256 |
| result digits | 128 |
| rendered characters | 512 |
| Decimal context precision | 256 |

`DecimalTuple` is inspected before fixed rendering. Estimated output length must
fit before `format(value, "f")` is called. Invalid operation, division by zero,
overflow, underflow and clamping are normalized to typed `ToolInputError`.


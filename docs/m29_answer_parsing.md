# M-29 Answer Parsing

Trusted parsing accepts bounded numeric-with-unit answers, RU/EN unit aliases, element count maps, atomic-weight intervals, controlled choices, and structured step sequences. Free text remains assistive until explicitly confirmed.

Float/bool API values, NaN/infinity, expressions, code, duplicate/conflicting maps, malformed units, wrong-case/unknown symbols, oversized text, and invalid step schemas are rejected. Decimal rendering preserves the full coefficient and never normalizes under an implicit 28-digit context.

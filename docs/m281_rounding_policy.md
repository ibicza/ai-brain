# Chemistry Rounding Policy

Rendering policy 2.0 uses decimal significant figures and `ROUND_HALF_EVEN`.
The supported range is 1 through 12 significant digits. Trailing zeros preserve
declared significance, and large/small values can use scientific notation.

Every rounded result stores both `exact_internal_value` and `rendered_value`,
plus digits, mode, and whether rounding changed the display. Interval endpoints
are rounded independently. Arithmetic and provenance always use exact internal
Decimal values; a rendered string is never fed back into a calculation.

Acceptance covers integers, small decimals, scientific values, halfway cases,
trailing zeros, intervals, recurring division, entities, Avogadro's exact
constant, and conventional molar mass.

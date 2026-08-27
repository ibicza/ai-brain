# M-28 Atomic-Weight Policy

Default calculations use `CONVENTIONAL_CLASSROOM_VALUE_FROM_CIAAW_ABRIDGED_2024`.

The data model preserves whether the standard value is a `SINGLE` or `INTERVAL`, plus the conventional value. Interval molar mass sums lower bounds and upper bounds independently. It never uses an interval midpoint. Conventional results always warn that conventional atomic weights are not exact constants.

Elements without an approved conventional value are excluded from trusted calculation. M-28 has 33 approved computational elements: 21 single-value and 12 interval elements, all with a conventional classroom value.

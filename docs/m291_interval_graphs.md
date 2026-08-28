# M-29.1 interval graphs

Standard atomic-weight intervals and interval molar masses are represented as exact `{lower, upper}` values. Multiplication, addition and supported unit conversion propagate both endpoints; negative scaling normalizes endpoint order. The verifier requires lower <= upper at every interval comparison.

Display rounding is recomputed independently for each endpoint. The final result must equal the completed source result; midpoint collapse is not accepted.

The catalog contains nine interval answer graphs. Acceptance mutates interval roots across its 2,000-case graph battery and accepts zero. Independent fixtures include midpoint-collapse cases, and interval hint leakage rejects endpoint pairs and the trivial midpoint.

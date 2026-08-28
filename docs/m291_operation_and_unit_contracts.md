# M-29.1 operation and unit contracts

The verifier independently evaluates immutable contracts for MULTIPLY, ADD, DIVIDE, UNIT_NORMALIZATION, MOLE_RELATION, AVOGADRO_RELATION, ROUND_DISPLAY and FINAL_RESULT.

MULTIPLY accepts a typed count multiplier; ADD requires equal input/output dimensions; DIVIDE requires exact arity and a nonzero denominator. Unit normalization requires equal dimensions, a bound source unit and one exact supported conversion factor. Mole and Avogadro relations accept only the declared physical direction and dimensions.

Known units are closed to g, kg, mol, mmol, mol^-1, g/mol, kg/mol, u and entities. Unknown units and unit/dimension mismatches fail. ROUND_DISPLAY preserves the exact typed value and unit while independently reconstructing and applying the rounding specification.

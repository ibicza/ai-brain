# M-28 Chemistry Units and Rounding

Accepted mass units are `g` and `kg`; amount units are `mol` and `mmol`; molar-mass units are `g/mol` and `kg/mol`. Entity types are `atoms`, `molecules`, and `formula_units`.

Inputs are bounded canonical Decimal values. Negative and non-finite values and float objects are rejected. Entity input must be an integer. Internal precision is 80 Decimal digits. Result artifacts retain unrounded canonical values; the renderer policy is versioned separately.

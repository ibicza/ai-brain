# M-29.1 hint leakage and targeting

Every `MisconceptionCode` maps to a targeted strategy or GENERIC_ONLY. Targeted hints are used only for EXACT_MATCH diagnoses; conservative/ambiguous diagnoses receive generic guidance.

Independent evaluation passes actual grading diagnoses into hint generation. Development results: 120 independently tested targeted hints and 0 wrong targeted hints.

Before FULL_SOLUTION, typed leakage verification rejects the exact value, rendered/rounded/scientific form, equivalent units, interval endpoint pairs and midpoint, reordered composition maps and Unicode numeric variants. Hints progress through concept, next operation, substitution and one non-final intermediate result; internal node IDs are metadata, not primary text.

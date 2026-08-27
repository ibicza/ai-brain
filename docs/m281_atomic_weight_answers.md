# Atomic-Weight Answers

`AtomicWeightAnswerBundle` is a typed schema-v2 response containing exact
symbol, atomic number, standard kind, standard nominal/uncertainty or interval,
abridged value/uncertainty, source/evidence/derivation hashes, current
FactMemory snapshot hash, warnings, and answer hash.

Supported requests can select standard, abridged, or all fields. Shape is
validated: interval elements cannot masquerade as single values, and single
elements cannot omit their uncertainty. All 33 elements are accepted by exact
symbol and localized reviewed name.

Atomic weight is dimensionless. Molar-mass tools produce `g/mol` or `kg/mol`
and explicitly identify the chosen atomic-weight mode.

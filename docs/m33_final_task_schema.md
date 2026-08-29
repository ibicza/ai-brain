# M-33 final task schema

The sealed corpus requires exactly four bundles and at least 500 exact semantic
keys: 150 kinematics, 125 biology, 100 history, and 125 Java tasks. Every task
contains an operation, target record/rule, requested unknown, normalized givens,
units, conditions, expected answer semantics, support expectation, and golden
hash.

Kinematics covers multiple unknowns, signs, rational values, compatible unit
conversions, applicability omission, incompatible units, and nonlinear
abstention. Biology covers definitions, taxonomy/part-whole, stages, source
attribution, exceptions, and insufficient evidence. History covers chronology,
attribution, distinct interpretations, disagreement, causal attribution, and
insufficient evidence. Java covers signatures, overloads, parameters, returns,
generics, exceptions, deprecation/since, wording, unknowns, version mismatch,
and compile/run capability abstention.

IDs, order, wording, language, and timestamps are excluded from semantic
identity. Exact duplicates fail the run and near-duplicate clusters are emitted
as a separate statistic.

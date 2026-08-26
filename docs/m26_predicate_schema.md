# M-26 Predicate Schema

`PredicateDefinition` binds subject type, object FactValue kind, `SINGLE`/`MULTI` cardinality, `ATEMPORAL`/`VALID_INTERVAL`/`EVENT` temporal mode, qualifier kinds, optional unit dimension, conflict-key qualifiers, overlap policy, and schema version.

Conflict detection is generic. For an active `SINGLE` predicate, different values conflict when subject, predicate, conflict qualifiers, and valid-time overlap match. Different `MULTI` values do not conflict automatically.

Unknown predicates, invalid qualifier kinds, wrong subject types, and wrong value kinds fail closed before approval or commit.

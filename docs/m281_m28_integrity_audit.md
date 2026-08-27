# M-28 Integrity Audit

## Scope

M-28 established the bounded introductory-chemistry domain, but its trusted
surface was not yet sufficient for release. The audit found source attribution,
current-state binding, numeric bounds, atomic-weight shape, symbol case, entity
semantics, rounding, and acceptance-diversity gaps.

## Closed Findings

- Derived JSON is now classified as `DETERMINISTIC_DERIVED_EXTRACT`, never as
  an official primary source.
- Every production chemistry claim binds reviewed evidence, a derived extract,
  its derivation record, and a hash-pinned upstream snapshot.
- Knowledge snapshots bind current claim, evidence, source, and event-derived
  state hashes. Retraction, supersession, contradiction, and conflict fail closed.
- Chemistry and router numeric inputs share one bounded `Decimal` parser.
- Standard atomic weights retain single-value uncertainty or interval shape.
- Element symbols are exact-case identifiers; names remain localized aliases.
- Formula-entity and total-atom semantics are distinct and preserve the formula.
- Significant-figure rendering applies `ROUND_HALF_EVEN`; internal values remain
  unchanged.
- Acceptance uses distinct semantic cases rather than repeated strings.

## Compatibility

M-28 data remains frozen. Chemistry domain 1.1.0 uses schema v2 and explicitly
requires v1 packs to be rebuilt from frozen sources.

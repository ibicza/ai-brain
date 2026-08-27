# M-28.1 Chemistry Integrity Report

## Decision

Outcome A: the bounded chemistry domain is trusted. Source chain, current-state
knowledge, numeric safety, educational semantics, routing, replay, exact-H4
local/Karina gates, and evidence-only diff all pass.

Implementation H4:
`6344bd2860ccc354196a41ab99895b4d59042859`.

## Delivered

Domain 1.1.0/schema 2 adds hash-pinned official snapshots and deterministic
derivations, CIAAW uncertainty-aware typed answers, event-derived current-state
snapshots, shared bounded Decimal handling, exact symbol case, explicit entity
bases, actual significant-figure rounding, replay v2, diverse acceptance, update
simulations, and mixed performance measurement.

## Limitations

- Only 33 selected elements; no full periodic-table domain.
- Classroom values are CIAAW abridged values with retained uncertainty.
- Natural-variability envelope is not full measurement uncertainty propagation.
- No compound ontology or automatic molecule/formula-unit classification.
- Total atoms require an explicit formula.
- No hydrates, charges, isotopes, reaction chemistry, or runtime network.
- No automatic calculated-fact writes; controlled RU/EN grammar remains finite.

## Next Step

Proceed to M-29 educational explanation and exercise layers without broadening
the trusted chemistry core implicitly. New knowledge still enters only through
reviewed source/derivation and current-state FactMemory contracts.

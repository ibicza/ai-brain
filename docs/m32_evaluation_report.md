# M-32 evaluation report

The independent oracle contains 636 expected typed proposal locations across four source genres. The deterministic rebuild produced 643 segments and 636 proposals: 489 deterministic, 64 empirical, 2 interpretive, 1 contested, and 80 normative.

Proposal counts by kind: `CAUSAL_RULE` 1, `CLAIM_SCHEMA` 80, `CONCEPT` 68, `DEFINITION` 155, `ENTITY_TYPE` 110, `EQUATION_RULE` 1, `EXAMPLE` 12, `INTERPRETATION` 2, `QUANTITY_TYPE` 4, `TAXONOMY_EDGE` 109, `TEMPORAL_RELATION` 64, and `TEST_CASE` 30.

For the bounded fixtures, proposal precision, recall, verified precision, coverage, source-span exactness, field exactness, capability detection, and conflict detection are 1.000000. Abstention and review-required rate are 0.000000 because all four fixtures use the explicit structured grammar. Wrong automatically verified proposals: 0.

Scale gates exercise 2,000 IR mutations, 2,000 provider/capability mutations, 1,000 pack/install mutations, 1,000 ambiguity cases, and 500 held-out tasks.

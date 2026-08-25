# M-25.1 Semantic Equivalence Report

## Result

Stage 2 schema v2 separates exact structural identity from observable Stage-1 effect identity.

| Item | Count |
|---|---:|
| structural skills | 89 |
| semantic effect classes | 57 |
| singleton classes | 41 |
| two-member MERGE_TWO classes | 12 |
| six-member MERGE_THREE classes | 4 |
| order-sensitive classes | 24 |
| order-insensitive classes | 33 |

`MERGE_TWO` and `MERGE_THREE` normalize commuting drains to one destination. `DROP_THEN_TRANSFER` retains role and phase order. NOOP has one observable effect class. CLEAR and DRAIN retain role identity.

Exact structured retrieval still returns one structural SkillRecord. Semantic retrieval returns one deterministic canonical representative and evidence containing the effect hash, all class members, proof kind, structural match, and whether canonical structural identity differs.

Registry validation now recomputes every manifest count, all semantic class counts, registry/RuleMemory hashes, Stage-1 version, and Stage-2 schema. Tests corrupt every count independently after recomputing the outer manifest hash; every mutation is rejected.

The equivalence proof kinds are exact Stage-1 normal form, commuting same-destination drains, and order-preserved phase semantics. No learned component participates.

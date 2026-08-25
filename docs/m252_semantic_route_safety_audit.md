# M-25.2 Semantic Route Safety Audit

## Baseline

- Source branch: `exp/stage2-skill-registry-fair-retest`.
- Source commit: `404e5393385c14bb21a4e68e2f99ea8f57031809`.
- Stage-2 schema: v2.
- SkillRegistry schema: v2.
- Installed structural skills: 89.
- Groups previously called semantic-effect classes: 57.
- Accepted M-25.1 outcome: B; learned retrieval is assistive-only.

No M-25.1 blind target was reopened during this audit.

## Unsafe V2 Behavior

`retrieve_semantic_signature()` computed a normalized effect hash, selected the
lexicographically deterministic canonical member, and returned
`EXACT_MATCH`, `exact_match=true`, and `SELECT_EXACT`. For MERGE source-order
permutations, the selected canonical member could have a different
`ProgramSpecification` hash from the request.

The normal `CONFIRM_SELECTION` path then bound only the selected
`specification_hash`. It did not bind both requested and selected structures,
equivalence scope, or class membership. Dispatch therefore had no way to tell an
exact structural selection from a final-state-only substitution.

Relevant v2 locations were:

- `stage2/retrieval.py::retrieve_semantic_signature`: canonical substitution and
  `EXACT_MATCH` construction.
- `stage2/retrieval.py::_result`: `exact_match=true` persistence.
- `stage2/service.py::prepare_selection`: candidate and generic evidence binding.
- `stage2/service.py::confirm_selection`: ordinary `CONFIRM_SELECTION`.
- `stage2/service.py::_validate_dispatch`: selected-record validation without the
  requested structural hash or equivalence scope.
- `tests/test_m25_skill_registry.py`: canonical-member equality and canonical
  dispatch were explicitly permitted.

## Observability Counterexamples

The generated state battery includes all-zero, basis, mixed, and larger-count
states. The following representative executions use mixed nonzero sources.

| Family | First specification | Second specification | Final-state effect | First action stream | Second action stream |
|---|---|---|---|---|---|
| MERGE_TWO | `d860d95a...137619` | `89494276...0848fc` | `01be337b...7954f1` | `1e507f58...7c6fbb` | `24deec2b...d88931` |
| MERGE_THREE | `989a63c5...70b8f` | `201b9432...887a9` | `4840eb7a...578f65` | `2deb36ee...438d3e` | `6c1c6638...7ae82e` |

For both pairs:

- final register states are equal;
- structural specification hashes differ;
- ordered captured actions differ;
- reconstructed intermediate-state sequences differ;
- `action_stream_hash` values differ;
- full execution identity is false.

## V3 Audit Conclusion

The 57 groups are valid final-register-state classes, not complete execution
equivalence classes. Production routing must default to structural identity and
must never silently use these groups as exact execution authority.

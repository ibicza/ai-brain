# M-22.3 Large Benchmark Report

## Manifest

```json
{
  "action_distribution": {
    "DROP_ONE": 18364,
    "HALT": 6700,
    "MOVE_ONE": 28503
  },
  "alpha_normalized_overlap": 0,
  "clause_count_distribution": {
    "1": 1,
    "2": 2,
    "3": 2,
    "4": 1,
    "8": 6694
  },
  "exact_ast_overlap": 0,
  "heldout_normalized_ast_templates": 200,
  "heldout_program_instances": 500,
  "kind": "m223_stage1_validation",
  "model_visible_target_ids": false,
  "normalized_ast_overlap": 0,
  "predicate_count_distribution": {
    "0": 1,
    "1": 7,
    "2": 5,
    "3": 53554
  },
  "primitive_overlap": 5,
  "seed": 2237,
  "specification_type_distribution": {
    "2_clause_drop": 1,
    "2_clause_transfer": 1,
    "3_clause_transfer": 1,
    "3_clause_transfer_drop": 1,
    "4_clause_transfer": 1,
    "8_clause_drop": 3,
    "8_clause_transfer_drop": 6691,
    "one_clause_noop": 1
  },
  "train_specifications": 5000,
  "validation_specifications": 1000,
  "variable_role_distribution": {
    "A": 6699,
    "B": 6698,
    "C": 6697,
    "D": 5138
  }
}
```

## Candidate Space

| requested | raw_generated | static_valid | abstract_valid | alpha_unique | semantic_classes | actual_searched | wall_time_sec |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | 1000 | 1000 | 738 | 1000 | 577 | 1000 | 1.3864 |
| 10000 | 10000 | 10000 | 7366 | 10000 | 4919 | 10000 | 15.4486 |

## Full Spec Templates

{
  "budget_exhausted": 0.0,
  "candidates_to_first_accepted": 81.215,
  "property_synthesis_success": 1.0,
  "semantic_correct": 1.0,
  "unsupported": 0.0,
  "wall_time_sec": 0.0035757560250203823
}
# M-22.3 Stage-1 Acquisition Validation Report

## Checks

- local/remote ruff + pytest + CUDA smoke: `passed`
- commit: `9aaefab`

## M-22.2 Audit

- hardcoded metric findings after patch: `0`
- target leakage count: `0`

## Dataset Verification

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

## Candidate Spaces Actually Used

| requested | raw_generated | typed_valid | static_valid | abstract_valid | alpha_unique | semantic_classes | actual_searched | actual_verified | wall_time_sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | 1000 | 1000 | 1000 | 738 | 1000 | 577 | 1000 | 738 | 1.3864 |
| 10000 | 10000 | 10000 | 10000 | 7366 | 10000 | 4919 | 10000 | 7366 | 15.4486 |

## Full-Spec CEGIS At Scale

{
  "budget_exhausted": 0.0,
  "candidates_to_first_accepted": 81.215,
  "property_synthesis_success": 1.0,
  "semantic_correct": 1.0,
  "unsupported": 0.0,
  "wall_time_sec": 0.0035757560250203823
}

## Heldout Instances

{
  "budget_exhausted": 0.0,
  "candidates_to_first_accepted": 5390.776,
  "property_synthesis_success": 1.0,
  "semantic_correct": 1.0,
  "unsupported": 0.0,
  "wall_time_sec": 0.003929596231988399
}

## Demonstrations-Only CEGIS

{
  "entropy": {
    "active_queries": 4.54,
    "ambiguous": 0.67,
    "correct_identified_class": 0.33,
    "false_selected_program": 0.0,
    "remaining_semantic_classes": 4.9,
    "selected": 0.33,
    "unsupported": 0.0,
    "wall_time_sec": 0.021316844770917668
  },
  "max_partition": {
    "active_queries": 4.54,
    "ambiguous": 0.67,
    "correct_identified_class": 0.33,
    "false_selected_program": 0.0,
    "remaining_semantic_classes": 4.9,
    "selected": 0.33,
    "unsupported": 0.0,
    "wall_time_sec": 0.021289575848495588
  },
  "random": {
    "active_queries": 4.81,
    "ambiguous": 0.92,
    "correct_identified_class": 0.08,
    "false_selected_program": 0.0,
    "remaining_semantic_classes": 47.52,
    "selected": 0.08,
    "unsupported": 0.0,
    "wall_time_sec": 0.0044071497909317255
  }
}

## Diverse Mutation Sweep

{
  "accepted": 0.1728,
  "false_accept": 0.0,
  "known_incorrect": 0.8272
}

## RuleMemory Reuse

{
  "candidate_rank": 50.5,
  "execution_retention": 1.0,
  "reload_retention": 1.0,
  "stored": 1.0
}

## Sequential Acquisition

{
  "candidate_rank": 55.0,
  "distinct_acquired_rules": 55.0,
  "execution_retention": 1.0,
  "latency_ms": 14531.520331000502,
  "memory_size": 55.0,
  "semantic_duplicate_count": 0.0,
  "step": 55.0
}

Final sequential checkpoint:

{
  "candidate_rank": 100,
  "distinct_acquired_rules": 100,
  "execution_retention": 1.0,
  "latency_ms": 27704.637442002422,
  "memory_size": 100,
  "semantic_duplicate_count": 0,
  "step": 100
}

## Novelty Detection

{
  "auprc": 1.0,
  "auroc": 1.0,
  "false_known_rate": 0.0,
  "false_novel_rate": 0.0,
  "known_count": 100,
  "known_recall": 1.0,
  "novel_abstention": 1.0,
  "novel_count": 100,
  "threshold": 1.0,
  "validation_only_threshold": true
}

## Learned Guidance

{
  "bfs_candidates": 5742.216666666666,
  "bfs_median_candidates": 6803.0,
  "mdl_candidates": 5742.216666666666,
  "mdl_median_candidates": 6803.0,
  "random_candidates": 3223.775,
  "random_median_candidates": 2593.0,
  "structured_candidates": 2110.1833333333334,
  "structured_median_candidates": 2220.0,
  "success": 1.0
}

## Subprogram Search

{
  "depth": 2.25,
  "plans_evaluated": 415.0,
  "success": 1.0,
  "target_sequence_supplied": 0.0,
  "wall_time_sec": 0.050021907671034566
}

## Negative Controls

{
  "accepted": 0.0,
  "checked_candidates": 40.0
}

## Manual Semantic Inspection

{
  "ambiguities": 20,
  "demo_identifications": 20,
  "rule_memory_reload_executions": 20,
  "successful_full_spec": 20,
  "unsupported_tasks": 20,
  "verifier_rejections": 20
}

## Final Decision

OUTCOME A: Freeze Stage 1 around structured specification + generic grammar + property verifier + CEGIS + active queries + RuleMemory + exact interpreter.

Next: M-23 controlled language-to-spec frontend

# M-22 M-21 Compiler Failure Audit

M-21 whole-AST compiler accuracy hid which AST slots failed. This audit compares predicted semantic hashes from `runs/m21_neural_symbolic_interpreter/compiler_eval.json` against known target/predicted ASTs when available.

## M-21 Whole AST Metrics

| name | count | deterministic_parser_exact | semantic_exact |
| --- | --- | --- | --- |
| heldout_template | 40 | 1.0000 | 0.0000 |
| seen_template | 80 | 1.0000 | 0.9000 |

## Slot Accuracy

| name | accuracy | correct | incorrect |
| --- | --- | --- | --- |
| clause_count | 0.4000 | 8 | 12 |
| predicate_count | 0.4000 | 8 | 12 |
| predicate_kind | 0.4000 | 8 | 12 |
| predicate_variable | 0.4000 | 8 | 12 |
| action_kind | 0.0000 | 0 | 20 |
| source_variable | 0.4000 | 8 | 12 |
| destination_variable | 0.0000 | 0 | 20 |
| binding | 1.0000 | 20 | 0 |
| ast_validity | 1.0000 | 20 | 0 |
| semantic_equivalence | 0.0000 | 0 | 20 |

## First Incorrect Slot Samples

| split | family | first_incorrect_slot |
| --- | --- | --- |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| seen_template | move_then_drop | action_kind |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | move_move_then_drop | clause_count |
| heldout_template | drop_move_then_drop | clause_count |
| heldout_template | drop_move_then_drop | clause_count |
| heldout_template | drop_move_then_drop | clause_count |
| heldout_template | drop_move_then_drop | clause_count |

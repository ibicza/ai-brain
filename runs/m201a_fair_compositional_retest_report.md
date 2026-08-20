# M-20.1a Fair Compositional Retest

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB`
- model config: `arithmetic_3m`
- sequence length: `256`

## M-20.1 Starting Point

M-20.1 reported binding aggregate `0.8889`, primitive predicate/action success, but failed single-clause, alpha-renaming, heldout program, and MERGE_TWO. M-20.1a retests the confounded axes separately.

- seed: `2031`
- model: `arithmetic_3m` with `relative` positions
- run steps: `{"binding_lm": 3000, "curriculum_no_replay_lm": 5000, "curriculum_replay25_lm": 5000, "curriculum_replay50_lm": 5000, "flat_balanced_lm": 7000, "single_clause_base_lm": 5000}`
- prior M-20.1 report present: `True`

## Binding Metric Decomposition

| split | accuracy | invalid |
|---|---:|---:|
| binding_l2p_seen | 0.6250 | 0.0000 |
| binding_l2p_heldout | 0.3281 | 0.0000 |
| binding_p2l_seen | 1.0000 | 0.0000 |
| binding_p2l_heldout | 0.9375 | 0.0000 |
| binding_full_table_seen | 0.1250 | 0.0000 |
| binding_full_table_heldout | 0.0000 | 0.0000 |

Point binding remains below gate; downstream composition should not be blamed alone.

## Fair Alpha-Renaming

| split | accuracy | invalid |
|---|---:|---:|
| alpha_known | 0.7292 | 0.0000 |

## Single-Clause Fit Ladder

| split | accuracy | invalid |
|---|---:|---:|
| single_clause_seen_seen_binding | 0.9583 | 0.0000 |
| single_clause_new_seen_binding | 0.5208 | 0.0000 |
| single_clause_seen_heldout_binding | 0.9167 | 0.0000 |
| single_clause_new_heldout_binding | 0.6250 | 0.0000 |

## Primitive Retention Across Curriculum

| run | binding_l2p_heldout | binding_p2l_heldout | predicate_heldout | action_heldout | single_clause_seen_seen_binding | program_seen |
|---|---|---|---|---|---|---|
| binding_lm | 0.3281 | 0.9375 | 0.5000 | 0.0662 | 0.0833 | 0.1667 |
| single_clause_base_lm | 0.3594 | 0.2969 | 1.0000 | 0.2132 | 0.8125 | 0.1864 |
| flat_balanced_lm | 0.4219 | 0.1875 | 1.0000 | 0.3088 | 0.8333 | 0.9463 |
| curriculum_no_replay_lm | 0.3125 | 0.1406 | 0.7734 | 0.1434 | 0.7188 | 1.0000 |
| curriculum_replay25_lm | 0.5781 | 0.2656 | 1.0000 | 0.4853 | 0.9167 | 0.9737 |
| curriculum_replay50_lm | 0.6875 | 0.2812 | 1.0000 | 0.6801 | 0.9583 | 1.0000 |

## Replay Ablation

| run | program_seen | heldout_binding | heldout_program | merge_two_seen |
|---|---|---|---|---|
| curriculum_no_replay_lm | 1.0000/1.0000 | 0.9386/0.8542 | 0.2799/0.1771 | 0.7705/0.2552 |
| curriculum_replay25_lm | 0.9737/0.9844 | 0.9693/0.9635 | 0.1799/0.1354 | 0.6235/0.0885 |
| curriculum_replay50_lm | 1.0000/1.0000 | 1.0000/1.0000 | 0.1896/0.1250 | 0.5543/0.0911 |

## Flat vs Curriculum

| run | program_seen | single_clause_new_heldout_binding | heldout_program | merge_two_seen |
|---|---|---|---|---|
| flat_balanced_lm | 0.9463/0.7995 | 0.3073 | 0.1299/0.1458 | 0.8869/0.5729 |
| curriculum_replay25_lm | 0.9737/0.9844 | 0.6250 | 0.1799/0.1354 | 0.6235/0.0885 |
| curriculum_replay50_lm | 1.0000/1.0000 | 0.6250 | 0.1896/0.1250 | 0.5543/0.0911 |

## Seen Fit Gate

| check | passed |
|---|---:|
| action | false |
| point_binding_l2p | false |
| point_binding_p2l | false |
| policy_program_seen_closed_loop | true |
| predicate | true |
| program_seen_closed_loop | true |
| program_seen_one_step | true |
| single_clause_seen | false |
| teacher_forced | false |
| overall | false |

## Real Teacher-Forced Clause Diagnostic

| split | accuracy | invalid |
|---|---:|---:|
| teacher_forced_clause_seen | 0.7363 | 0.0000 |
| teacher_forced_clause_heldout_binding | 0.7840 | 0.0000 |
| teacher_forced_clause_merge_two | 0.6964 | 0.0000 |

## Clause Selection Diagnostic

| split | accuracy | invalid |
|---|---:|---:|
| clause_selection_seen | 0.9726 | 0.0000 |

## LM Action vs Policy Head

| split | LM one/closed | policy one/closed |
|---|---:|---:|
| program_seen | 1.0000/1.0000 | 0.9962/0.9818 |
| heldout_binding | 1.0000/1.0000 | 0.9770/0.9688 |
| heldout_program | 0.1896/0.1250 | 0.2917/0.2240 |
| merge_two_seen | 0.5543/0.0911 | 0.7600/0.4193 |

## Role Embeddings if gated

Not run. The fit gate was not reached with plain token DSL and replay variants, so role embeddings remain a later controlled ablation.

## MERGE_TWO Phase Accuracy

| phase | count | accuracy |
|---|---:|---:|
| A_TO_B_SWITCH | 320 | 0.4531 |
| FINAL_HALT | 384 | 1.0000 |
| PHASE_A_MOVE | 1344 | 0.5365 |
| PHASE_B_MOVE | 640 | 0.3750 |

## Error Propagation

| split | length bucket | episodes | success | first-error step avg |
|---|---:|---:|---:|---:|
| merge_two_seen | 0_10 | 360 | 0.0972 | 0.52 |
| merge_two_seen | 11_20 | 24 | 0.0000 | 0.83 |
| merge_two_11_20 | 21_50 | 240 | 0.0000 | 0.00 |
| merge_two_21_50 | 21_50 | 12 | 0.0000 | 0.00 |
| merge_two_21_50 | 51_plus | 108 | 0.0000 | 0.00 |

## Heldout Binding

| split | one-step | closed-loop | invalid |
|---|---:|---:|---:|
| heldout_binding | 1.0000 | 1.0000 | 0.0000 |

## Heldout Program

| split | one-step | closed-loop | invalid |
|---|---:|---:|---:|
| heldout_program | 0.1896 | 0.1250 | 0.1615 |

## MERGE_TWO Ladder

| split | one-step | closed-loop | invalid |
|---|---:|---:|---:|
| merge_two_seen | 0.5543 | 0.0911 | 0.0000 |
| merge_two_11_20 | 0.5167 | 0.0000 | 0.0000 |
| merge_two_21_50 | 0.5391 | 0.0000 | 0.0000 |

## Closed-Loop MERGE_TWO if gated

Closed-loop MERGE_TWO was run as a diagnostic, but should not be interpreted as true OOD success because the seen-fit gate was not fully passed.

## Structural Overlap Audit

```json
{
  "exact_prompt_overlap": 748,
  "forbidden_prompt_count": 0,
  "normalized_ast_overlap_heldout_program": 0,
  "template_overlap_heldout_program": 0,
  "template_overlap_merge_two": 0
}
```

## Interpretation

OUTCOME E: fair retest still fails the seen-fit prerequisite gate; do not make OOD claims.

## Recommended Architecture

Fix curriculum/objective and seen-fit reliability before further OOD interpretation.

## Checks

- local/remote ruff + pytest + CUDA smoke: passed
- commit hash at run: `26673e3`

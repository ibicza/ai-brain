# M-17 Clean Compositional Reasoning Curriculum

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `9f5b7d4`
- device: `cuda:0` (NVIDIA GeForce RTX 3050 Laptop GPU)

## Dataset Design

- task types: ADD, SUB, MISSING_ADDEND, COMPARE_NUMBERS, COMPARE_SUM, STATE_ADD, STATE_SUB
- prompts: deterministic symbolic prompts plus balanced Russian state-change templates
- answers: `FINAL <value>`; composition answers also include `STEP1` and `STEP2` diagnostics
- numeric tokenization: `digit_safe`
- ranges: symbolic and state primitives use two-digit operands `10..99`; subtraction is non-negative; composition uses two-digit operands with non-negative finals
- balancing: train/eval sampling is bucket-balanced by carry/borrow, output length, or relation where applicable; joint/staged datasets use equal task sampling
- train examples per primitive: 3000
- eval examples per split: 500

### Train/Eval Intersections

| split group | split | prompt intersection | duplicates |
|---|---:|---:|---:|
| add | eval_seen | 500 | 0 |
| add | eval_train | 500 | 0 |
| add | eval_unseen | 0 | 0 |
| compare_numbers | eval_seen | 500 | 0 |
| compare_numbers | eval_train | 500 | 0 |
| compare_numbers | eval_unseen | 0 | 0 |
| compare_sum | eval_seen | 500 | 0 |
| compare_sum | eval_train | 500 | 0 |
| compare_sum | eval_unseen | 0 | 0 |
| missing_addend | eval_seen | 500 | 0 |
| missing_addend | eval_train | 500 | 0 |
| missing_addend | eval_unseen | 0 | 0 |
| state_add | eval_seen | 0 | 0 |
| state_add | eval_train | 500 | 0 |
| state_add | eval_unseen | 0 | 0 |
| state_sub | eval_seen | 0 | 0 |
| state_sub | eval_train | 500 | 0 |
| state_sub | eval_unseen | 0 | 0 |
| sub | eval_seen | 500 | 0 |
| sub | eval_train | 500 | 0 |
| sub | eval_unseen | 0 | 0 |
| composition | eval_add_sub_seen | 500 | 0 |
| composition | eval_add_sub_teacher_forced | 0 | 0 |
| composition | eval_add_sub_unseen | 0 | 0 |
| composition | eval_sub_add_seen | 500 | 0 |
| composition | eval_sub_add_teacher_forced | 0 | 0 |
| composition | eval_sub_add_unseen | 0 | 0 |

## Single Primitive Results

| task | train | seen | unseen | train loss | digit metrics | carry/borrow buckets |
|---|---:|---:|---:|---:|---|---|
| add | 0.9060 | 0.9100 | 0.9040 | 0.0316 | per_digit:0.9451, units:0.9760, tens:0.9260, hundreds:0.9096 | carry_bucket(final_carry:0.7771, no_carry:0.9641, units_carry:0.9701); output_length(2_digit:0.9671, 3_digit:0.7771) |
| compare_numbers | 0.9940 | 0.9980 | 0.9940 | 0.0000 | n/a | relation(GT:0.9960, LT:0.9920) |
| compare_sum | 0.8780 | 0.8960 | 0.8560 | 0.0019 | n/a | relation(EQUAL:0.7365, LEFT:0.9641, RIGHT:0.8675) |
| missing_addend | 0.8500 | 0.8480 | 0.8220 | 0.0104 | per_digit:0.9090, units:0.9160, tens:0.9020 | carry_bucket(final_carry:0.7108, no_carry:0.8862, units_carry:0.8683); output_length(2_digit:0.8772, 3_digit:0.7108) |
| state_add | 0.9100 | 0.0120 | 0.0020 | 0.1120 | per_digit:0.4966, units:0.0020, tens:0.8400, hundreds:0.9464 | carry_bucket(final_carry:0.0060, no_carry:0.0000, units_carry:0.0000); output_length(2_digit:0.0000, 3_digit:0.0060) |
| state_sub | 0.9200 | 0.0020 | 0.0000 | 0.0686 | per_digit:0.4470, units:0.0000, tens:0.8940 | borrow_bucket(borrow:0.0000, no_borrow:0.0000); output_length(2_digit:0.0000) |
| sub | 0.9140 | 0.9220 | 0.8880 | 0.0331 | per_digit:0.9390, units:0.9340, tens:0.9440 | borrow_bucket(borrow:0.8128, no_borrow:0.9329); output_length(2_digit:0.8880) |

## Joint Multitask Results

| run | task | single unseen | joint unseen | retention delta |
|---|---|---:|---:|---:|
| joint_all_3m | add | 0.9040 | 0.0500 | -0.8540 |
| joint_all_3m | compare_numbers | 0.9940 | 0.9540 | -0.0400 |
| joint_all_3m | compare_sum | 0.8560 | 0.6700 | -0.1860 |
| joint_all_3m | missing_addend | 0.8220 | 0.0660 | -0.7560 |
| joint_all_3m | state_add | 0.0020 | 0.0000 | -0.0020 |
| joint_all_3m | state_sub | 0.0000 | 0.0000 | 0.0000 |
| joint_all_3m | sub | 0.8880 | 0.0840 | -0.8040 |
| joint_symbolic_3m | add | 0.9040 | 0.0640 | -0.8400 |
| joint_symbolic_3m | compare_numbers | 0.9940 | 0.9840 | -0.0100 |
| joint_symbolic_3m | compare_sum | 0.8560 | 0.7900 | -0.0660 |
| joint_symbolic_3m | missing_addend | 0.8220 | 0.0780 | -0.7440 |
| joint_symbolic_3m | sub | 0.8880 | 0.0540 | -0.8340 |

## Staged Curriculum

| training stage | add | sub | missing_addend | compare_numbers | compare_sum | state_add | state_sub |
|---|---:|---:|---:|---:|---:|---:|---:|
| staged_1_stage1_add_sub_3m | 0.7580 | 0.8120 | n/a | n/a | n/a | n/a | n/a |
| staged_2_stage2_missing_compare_3m | 0.8380 | 0.9180 | 0.2820 | 0.9880 | n/a | n/a | n/a |
| staged_3_stage3_compare_sum_3m | 0.8860 | 0.9520 | 0.5840 | 0.9840 | 0.7300 | n/a | n/a |
| staged_4_stage4_state_3m | 0.9220 | 0.9280 | 0.6840 | 0.9920 | 0.8560 | 0.0020 | 0.0000 |

## Composition Results

| run | composition | trained/held-out | final NEM | step1 | step2 | teacher-forced |
|---|---|---|---:|---:|---:|---:|
| composition_holdout_sub_add_3m | add_sub_seen | trained | 0.0180 | 0.3740 | 0.0700 | 0.3140 |
| composition_holdout_sub_add_3m | add_sub_unseen | trained | 0.0040 | 0.3900 | 0.0480 | 0.3140 |
| composition_holdout_sub_add_3m | sub_add_seen | held-out | 0.0000 | 0.0000 | 0.0080 | 0.4620 |
| composition_holdout_sub_add_3m | sub_add_unseen | held-out | 0.0000 | 0.0000 | 0.0060 | 0.4620 |
| composition_seen_add_sub_sub_add_3m | add_sub_seen | trained | 0.0060 | 0.2520 | 0.0700 | 0.0020 |
| composition_seen_add_sub_sub_add_3m | add_sub_unseen | trained | 0.0040 | 0.2240 | 0.0540 | 0.0020 |
| composition_seen_add_sub_sub_add_3m | sub_add_seen | trained | 0.0000 | 0.2040 | 0.1020 | 0.0000 |
| composition_seen_add_sub_sub_add_3m | sub_add_unseen | trained | 0.0000 | 0.2020 | 0.0800 | 0.0000 |

## Symbolic vs Language Context Transfer

- ADD symbolic unseen: 0.9040; STATE_ADD language unseen: 0.0020
- SUB symbolic unseen: 0.8880; STATE_SUB language unseen: 0.0000
- Cross-training transfer is not mixed into the primary numeric benchmark; this section compares separately trained symbolic and language-grounded tasks.

## Tiny vs 5.29M Control

- tiny_control_joint_symbolic: {'add_unseen': 0.048, 'compare_numbers_unseen': 0.976, 'compare_sum_unseen': 0.644, 'missing_addend_unseen': 0.062, 'sub_unseen': 0.042}

## Failure Samples

- single_add_3m/seen: `ADD 11 + 97` expected `FINAL 108` predicted `FINAL 118`
- single_add_3m/train: `ADD 42 + 79` expected `FINAL 121` predicted `FINAL 111`
- single_add_3m/unseen: `ADD 52 + 35` expected `FINAL 87` predicted `FINAL 86`
- single_compare_numbers_3m/seen: `COMPARE 29 29` expected `FINAL EQUAL` predicted `FINAL LT`
- single_compare_numbers_3m/train: `COMPARE 58 59` expected `FINAL LT` predicted `FINAL EQUAL`
- single_compare_numbers_3m/unseen: `COMPARE 44 46` expected `FINAL LT` predicted `FINAL EQUAL`
- single_compare_sum_3m/seen: `COMPARE_SUM 23 + 93 | 44 + 72` expected `FINAL EQUAL` predicted `FINAL LEFT`
- single_compare_sum_3m/train: `COMPARE_SUM 97 + 12 | 99 + 10` expected `FINAL EQUAL` predicted `FINAL LEFT`
- single_compare_sum_3m/unseen: `COMPARE_SUM 17 + 55 | 26 + 46` expected `FINAL EQUAL` predicted `FINAL LEFT`
- single_missing_addend_3m/seen: `MISSING 99 + ? = 142` expected `FINAL 43` predicted `FINAL 53`
- single_missing_addend_3m/train: `MISSING 48 + ? = 145` expected `FINAL 97` predicted `FINAL 98`
- single_missing_addend_3m/unseen: `MISSING 91 + ? = 168` expected `FINAL 77` predicted `FINAL 67`

## Interpretation

Outcome E: some individual primitives remain below the minimum usable unseen threshold. Weak primitives: compare_sum, missing_addend, state_add, state_sub, sub.

## Recommended Next Milestone

Fix the weak individual primitives before drawing conclusions about composition.

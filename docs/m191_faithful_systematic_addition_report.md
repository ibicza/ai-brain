# M-19.1 Faithful Systematic Addition Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `e424e70`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## M-19 Methodology Audit

- M-19 clean in_range mixed the held-out digit-pair axis; M-19.1 clean ID excludes held-out digit pairs and asserts ID pairs are covered by train.
- M-19 RFFT put the rule text only in the target. M-19.1 puts the generic rule in the input for faithful rule following.
- M-19 length results were zero-shot 2-to-long extrapolation. M-19.1 uses staged 1, 1-2, 1-3, and 1-5 digit training.
- M-19 state_machine did not preserve a persistent copied state. M-19.1 Turing traces copy full A/B/O/C/H state and apply local edits.

## Corrected Split Verification

| split | count | range | digit lengths | result lengths | buckets | heldout pairs |
|---|---:|---|---|---|---|---:|
| clean_id | 240 | 10..69 | {'2': 240} | {'2': 196, '3': 44} | {'final_overflow': 44, 'internal_carry': 69, 'no_carry': 127} | 0 |
| digit_pair_ood | 240 | 10..69 | {'2': 240} | {'2': 186, '3': 54} | {'final_overflow': 54, 'internal_carry': 116, 'no_carry': 70} | 240 |
| length_1 | 60 | 0..9 | {'1': 60} | {'1': 40, '2': 20} | {'final_overflow': 20, 'no_carry': 40} | 0 |
| length_10 | 60 | 1049620340..9982639672 | {'10': 60} | {'10': 26, '11': 34} | {'final_overflow': 34, 'internal_carry': 25, 'no_carry': 1} | 0 |
| length_12 | 60 | 101220680622..997794542094 | {'12': 60} | {'12': 25, '13': 35} | {'final_overflow': 35, 'internal_carry': 25} | 0 |
| length_2 | 60 | 10..99 | {'2': 60} | {'2': 11, '3': 49} | {'final_overflow': 49, 'internal_carry': 1, 'no_carry': 10} | 0 |
| length_3 | 60 | 100..999 | {'3': 60} | {'3': 28, '4': 32} | {'final_overflow': 32, 'internal_carry': 17, 'no_carry': 11} | 0 |
| length_4 | 60 | 1006..9976 | {'4': 60} | {'4': 27, '5': 33} | {'final_overflow': 33, 'internal_carry': 20, 'no_carry': 7} | 0 |
| length_5 | 60 | 10191..98672 | {'5': 60} | {'5': 27, '6': 33} | {'final_overflow': 33, 'internal_carry': 23, 'no_carry': 4} | 0 |
| length_6 | 60 | 104260..996245 | {'6': 60} | {'6': 27, '7': 33} | {'final_overflow': 33, 'internal_carry': 25, 'no_carry': 2} | 0 |
| length_8 | 60 | 11260863..98731516 | {'8': 60} | {'8': 33, '9': 27} | {'final_overflow': 27, 'internal_carry': 33} | 0 |
| range_ood | 120 | 10..89 | {'2': 120} | {'2': 120} | {'internal_carry': 27, 'no_carry': 93} | 0 |
| train_pool | 2692 | 10..69 | {'2': 2692} | {'2': 2084, '3': 608} | {'final_overflow': 608, 'internal_carry': 758, 'no_carry': 1326} | 0 |

Prompt intersections max: `0`.
ID pair subset of train: `True`.

## Saturated ID Baseline

| train size | train final loss | clean ID | digit-pair OOD | range OOD | length 3 |
|---:|---:|---:|---:|---:|---:|
| 3000 | 0.000002 | 1.0000 | 0.0000 | 0.2000 | 0.0000 |
| 10000 | 0.000000 | 1.0000 | 0.0125 | 0.0000 | 0.0000 |
| 30000 | 0.000000 | 1.0000 | 0.0000 | 0.2083 | 0.0000 |

Clean ID gate >= .98: `True`.

## Local 200-State Transition Test

| eval | exact | avg tokens |
|---|---:|---:|
| transition_train/all_200 | 1.0000 | 15.00 |
| template_heldout/all_200 | 0.0550 | 12.14 |

## Faithful RFFT

| stage | len1 | len2 | len3 | len4 | len5 | len6 | len8 | len10 | len12 | digit-pair OOD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stage_a_1digit | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| stage_b_1_2digit | 0.9000 | 0.5500 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| stage_c_1_3digit | 1.0000 | 0.9167 | 0.7833 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.1167 |
| stage_d_1_5digit | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0333 |

## Faithful Turing Program

| stage | len1 | len2 | len3 | len4 | len5 | len6 | len8 | len10 | len12 | digit-pair OOD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stage_a_1digit | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| stage_b_1_2digit | 0.9000 | 0.8167 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| stage_c_1_3digit | 1.0000 | 1.0000 | 0.9167 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0333 |
| stage_d_1_5digit | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Real Length Curriculum

| variant | after 1 digit len1 | after 1-2 len2 | after 1-3 len3 | after 1-5 len5 | len8 | len12 |
|---|---:|---:|---:|---:|---:|---:|
| rfft | 1.0000 | 0.5500 | 0.7833 | 1.0000 | 0.0000 | 0.0000 |
| turing | 1.0000 | 0.8167 | 0.9167 | 1.0000 | 0.0000 | 0.0000 |

## Format Controls

| variant | len3 | len5 | len8 | digit-pair OOD |
|---|---:|---:|---:|---:|
| skipped: no faithful variant passed systematic OOD gate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Optional Verified Self-Improvement

skipped: 3-digit trained-length fit passed, but length extrapolation and/or digit-pair OOD failed, so self-generated samples would not be a faithful generalization signal.

## Capacity Sweep

eligible for a separate follow-up: clean ID fits, but both faithful methods fail systematic OOD after fitting trained lengths. Do not treat this report as evidence for scaling alone.

## Recommendation

D - clean ID and trained 1-5 digit curriculum fit, but length extrapolation and held-out digit-pair OOD still fail. This is curriculum-length fitting, not faithful systematic addition generalization.

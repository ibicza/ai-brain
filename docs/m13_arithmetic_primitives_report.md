# M-13 Arithmetic Primitive Decomposition Report

## Checks

- `uv run ruff format src tests`: passed (`51 files left unchanged`)
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: passed (`148 passed`)
- `uv run pytest tests\test_data_generation.py tests\test_cli.py -q`: passed (`84 passed`)
- `.\scripts\update-code-graph.ps1`: passed (`55 files, 538 nodes, 4718 edges`)
- Device used for training/eval: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`, 4GB)

## Implemented Primitive Task Types

- `arithmetic.digit_add_carry`: `DIGIT_ADD a=<digit> b=<digit> c=<carry>` -> `S <digit> C <carry>`
- `arithmetic.digit_sub_borrow`: `DIGIT_SUB a=<digit> b=<digit> borrow=<borrow>` -> `S <digit> B <borrow>`
- `arithmetic.add_2digit_no_carry`
- `arithmetic.add_2digit_with_carry`
- `arithmetic.sub_2digit_no_borrow`
- `arithmetic.sub_2digit_with_borrow`
- `arithmetic.missing_addend_simple`: target-known as subtraction
- `arithmetic.compare_sum_simple`: compute two sums, compare, output larger sum
- `arithmetic.double_step_simple`: add then subtract, metadata subset is `no_carry_no_borrow` or `carry_or_borrow`
- `compact_digit_trace`: short `OP/A/B/U/T/OUT` traces without verbose Russian text or long place-role tags

## Dataset Verification

| primitive | train | eval each | range train | range shifted-in | range digit-holdout | range far | train combos | holdout unseen frac | checks |
| --- | ---: | ---: | --- | --- | --- | --- | ---: | ---: | --- |
| digit_add_carry | 2000 | 500 | 0..9 (10) | 0..9 (10) | 0..9 (10) | 0..9 (10) | 160 | 1.000 | True |
| digit_sub_borrow | 2000 | 500 | 0..9 (10) | 0..9 (10) | 0..9 (10) | 0..9 (10) | 160 | 1.000 | True |
| add_2digit_no_carry | 5000 | 1000 | 10..58 (49) | 20..78 (58) | 20..79 (60) | 40..58 (19) | 40 | 0.273 | True |
| add_2digit_with_carry | 5000 | 1000 | 11..59 (45) | 21..79 (54) | 21..79 (53) | 41..99 (54) | 60 | 0.358 | True |
| sub_2digit_no_borrow | 5000 | 1000 | 10..59 (48) | 20..79 (58) | 20..79 (60) | 40..99 (58) | 40 | 0.273 | True |
| sub_2digit_with_borrow | 5000 | 1000 | 11..58 (48) | 21..78 (58) | 21..78 (58) | 41..98 (58) | 49 | 0.233 | True |
| missing_addend_simple | 5000 | 1000 | 1..108 (107) | 1..126 (121) | 0..99 (92) | 1..148 (147) | 99 | 0.234 | True |
| compare_sum_simple | 5000 | 1000 | 0..49 (50) | 20..79 (60) | 20..79 (60) | 50..99 (50) | 110 | 0.309 | True |
| double_step_simple | 8000 | 1500 | 0..98 (99) | 0..99 (100) | 0..99 (100) | 0..99 (100) | 208 | 0.218 | True |

## Digit-Combination Coverage


### digit_add_carry

- task_types: `arithmetic.digit_add_carry`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=160, eval_same=153, shifted-in=153, holdout=40, far=152
- digit-holdout unseen combo fraction vs train: 1.000

### digit_sub_borrow

- task_types: `arithmetic.digit_sub_borrow`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=160, eval_same=155, shifted-in=150, holdout=40, far=150
- digit-holdout unseen combo fraction vs train: 1.000

### add_2digit_no_carry

- task_types: `arithmetic.add_2digit_no_carry`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=40, eval_same=40, shifted-in=40, holdout=55, far=40
- digit-holdout unseen combo fraction vs train: 0.273

### add_2digit_with_carry

- task_types: `arithmetic.add_2digit_with_carry`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=60, eval_same=60, shifted-in=64, holdout=81, far=70
- digit-holdout unseen combo fraction vs train: 0.358

### sub_2digit_no_borrow

- task_types: `arithmetic.sub_2digit_no_borrow`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=40, eval_same=40, shifted-in=40, holdout=55, far=40
- digit-holdout unseen combo fraction vs train: 0.273

### sub_2digit_with_borrow

- task_types: `arithmetic.sub_2digit_with_borrow`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=49, eval_same=49, shifted-in=53, holdout=60, far=53
- digit-holdout unseen combo fraction vs train: 0.233

### missing_addend_simple

- task_types: `arithmetic.missing_addend_simple`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=99, eval_same=99, shifted-in=100, holdout=124, far=93
- digit-holdout unseen combo fraction vs train: 0.234

### compare_sum_simple

- task_types: `arithmetic.compare_sum_simple`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=110, eval_same=110, shifted-in=122, holdout=136, far=110
- digit-holdout unseen combo fraction vs train: 0.309

### double_step_simple

- task_types: `arithmetic.double_step_simple`
- answer_format: `compact_digit_trace`
- prompt checks: all_prompt_intersections_zero=True, all_task_types_present=True
- digit combos: train=208, eval_same=208, shifted-in=205, holdout=257, far=195
- digit-holdout unseen combo fraction vs train: 0.218


## Training Losses

| primitive | steps | final train loss | final eval loss | grad norm | trunc train/eval |
| --- | ---: | ---: | ---: | ---: | --- |
| digit_add_carry | 3000 | 0.028498 | 4.614924 | 1.3227 | 0/0 |
| digit_sub_borrow | 3000 | 0.302810 | 5.088445 | 2.4307 | 0/0 |
| add_2digit_no_carry | 5000 | 0.000013 | 6.911283 | 0.0006 | 0/0 |
| add_2digit_with_carry | 5000 | 0.004705 | 7.054229 | 0.2192 | 0/0 |
| sub_2digit_no_borrow | 5000 | 0.000011 | 8.366389 | 0.0005 | 0/0 |
| sub_2digit_with_borrow | 5000 | 0.000005 | 6.250493 | 0.0003 | 0/0 |
| missing_addend_simple | 5000 | 0.040226 | 2.846637 | 0.3082 | 0/0 |
| compare_sum_simple | 5000 | 0.055748 | 5.490729 | 0.4891 | 0/0 |
| double_step_simple | 8000 | 0.000889 | 3.367246 | 0.1409 | 0/0 |

## Final-Answer NEM Summary

| primitive | same | shifted-in | digit-holdout | far-range |
| --- | ---: | ---: | ---: | ---: |
| digit_add_carry | 0.4460 | 0.2740 | 0.1220 | 0.1600 |
| digit_sub_borrow | 0.1440 | 0.0760 | 0.0000 | 0.0640 |
| add_2digit_no_carry | 1.0000 | 0.4510 | 0.0160 | 0.4560 |
| add_2digit_with_carry | 0.9960 | 0.3440 | 0.0070 | 0.0640 |
| sub_2digit_no_borrow | 1.0000 | 0.3060 | 0.0000 | 0.0800 |
| sub_2digit_with_borrow | 1.0000 | 0.3280 | 0.0000 | 0.0660 |
| missing_addend_simple | 0.1380 | 0.0780 | 0.0090 | 0.0390 |
| compare_sum_simple | 0.1140 | 0.0060 | 0.0040 | 0.0000 |
| double_step_simple | 0.8133 | 0.3860 | 0.0407 | 0.1747 |

## Full Metrics

| primitive | split | full normalized EM | final NEM | false answer rate | empty rate | avg tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| digit_add_carry | same | 0.4460 | 0.4460 | 0.0000 | 0.0000 | 7.00 |
| digit_add_carry | shifted-in | 0.2740 | 0.2740 | 0.0000 | 0.0000 | 6.39 |
| digit_add_carry | digit-holdout | 0.1220 | 0.1220 | 0.0000 | 0.0000 | 6.34 |
| digit_add_carry | far-range | 0.1600 | 0.1600 | 0.0000 | 0.0000 | 5.88 |
| digit_sub_borrow | same | 0.1440 | 0.1440 | 0.0000 | 0.0000 | 7.00 |
| digit_sub_borrow | shifted-in | 0.0760 | 0.0760 | 0.0000 | 0.0000 | 6.31 |
| digit_sub_borrow | digit-holdout | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 6.30 |
| digit_sub_borrow | far-range | 0.0640 | 0.0640 | 0.0000 | 0.0000 | 5.97 |
| add_2digit_no_carry | same | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 39.00 |
| add_2digit_no_carry | shifted-in | 0.4500 | 0.4510 | 0.0000 | 0.0000 | 41.95 |
| add_2digit_no_carry | digit-holdout | 0.0000 | 0.0160 | 0.0000 | 0.0000 | 42.13 |
| add_2digit_no_carry | far-range | 0.4490 | 0.4560 | 0.0000 | 0.0000 | 42.56 |
| add_2digit_with_carry | same | 0.9960 | 0.9960 | 0.0000 | 0.0000 | 39.02 |
| add_2digit_with_carry | shifted-in | 0.3440 | 0.3440 | 0.0000 | 0.2960 | 27.86 |
| add_2digit_with_carry | digit-holdout | 0.0020 | 0.0070 | 0.0000 | 0.3150 | 27.15 |
| add_2digit_with_carry | far-range | 0.0640 | 0.0640 | 0.0000 | 0.5620 | 17.74 |
| sub_2digit_no_borrow | same | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 39.00 |
| sub_2digit_no_borrow | shifted-in | 0.2720 | 0.3060 | 0.0000 | 0.0000 | 38.83 |
| sub_2digit_no_borrow | digit-holdout | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 38.91 |
| sub_2digit_no_borrow | far-range | 0.0280 | 0.0800 | 0.0000 | 0.0000 | 38.00 |
| sub_2digit_with_borrow | same | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 39.00 |
| sub_2digit_with_borrow | shifted-in | 0.3110 | 0.3280 | 0.0000 | 0.1910 | 32.53 |
| sub_2digit_with_borrow | digit-holdout | 0.0000 | 0.0000 | 0.0000 | 0.1750 | 33.57 |
| sub_2digit_with_borrow | far-range | 0.0370 | 0.0660 | 0.0000 | 0.3440 | 27.12 |
| missing_addend_simple | same | 0.1370 | 0.1380 | 0.0000 | 0.0000 | 53.33 |
| missing_addend_simple | shifted-in | 0.0700 | 0.0780 | 0.0000 | 0.0000 | 53.80 |
| missing_addend_simple | digit-holdout | 0.0000 | 0.0090 | 0.0000 | 0.0000 | 52.91 |
| missing_addend_simple | far-range | 0.0210 | 0.0390 | 0.0000 | 0.0000 | 54.05 |
| compare_sum_simple | same | 0.0170 | 0.1140 | 0.0000 | 0.0000 | 110.16 |
| compare_sum_simple | shifted-in | 0.0000 | 0.0060 | 0.0000 | 0.0000 | 110.27 |
| compare_sum_simple | digit-holdout | 0.0000 | 0.0040 | 0.0000 | 0.0000 | 110.60 |
| compare_sum_simple | far-range | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 109.36 |
| double_step_simple | same | 0.8113 | 0.8133 | 0.0000 | 0.0000 | 76.60 |
| double_step_simple | shifted-in | 0.3820 | 0.3860 | 0.0000 | 0.0000 | 77.24 |
| double_step_simple | digit-holdout | 0.0260 | 0.0407 | 0.0000 | 0.0000 | 76.96 |
| double_step_simple | far-range | 0.1613 | 0.1747 | 0.0000 | 0.0000 | 77.38 |

## Double-Step Subset Metrics

| split | subset | count | final NEM |
| --- | --- | ---: | ---: |
| same | carry_or_borrow | 766 | 0.8368 |
| same | no_carry_no_borrow | 734 | 0.7888 |
| shifted-in | carry_or_borrow | 732 | 0.4208 |
| shifted-in | no_carry_no_borrow | 768 | 0.3529 |
| digit-holdout | carry_or_borrow | 777 | 0.0566 |
| digit-holdout | no_carry_no_borrow | 723 | 0.0235 |
| far-range | carry_or_borrow | 706 | 0.2252 |
| far-range | no_carry_no_borrow | 794 | 0.1297 |

## Failure Samples

### digit_add_carry

- prompt: `case 37903. DIGIT_ADD a=0 b=7 c=0`; expected: `S 7 C 0`; predicted: `S 9 C 0`
- prompt: `case 19484. DIGIT_ADD a=7 b=4 c=1`; expected: `S 2 C 1`; predicted: `S 1 C 1`
### digit_sub_borrow

- prompt: `case 18079. DIGIT_SUB a=7 b=3 borrow=1`; expected: `S 3 B 0`; predicted: `S 7 B 0`
- prompt: `case 43048. DIGIT_SUB a=2 b=2 borrow=0`; expected: `S 0 B 0`; predicted: `S 7 B 1`
### add_2digit_no_carry

- prompt: `case 32360. ADD2 60 + 20`; expected: `OP ADD / A 6 0 / B 2 0 / U 0 0 0 -> 0 0 / T 6 2 0 -> 8 0 / OUT 80`; predicted: `142 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706 8706`
- prompt: `case 11226. ADD2 55 + 23`; expected: `OP ADD / A 5 5 / B 2 3 / U 5 3 0 -> 8 0 / T 5 2 0 -> 7 0 / OUT 78`; predicted: `2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 / U 6 0 0 -> 8 0 / T 1 0 -> 5 0 / OUT 58 58`
### add_2digit_with_carry

- prompt: `case 20347. ADD2 76 + 47`; expected: `OP ADD / A 7 6 / B 4 7 / U 6 7 0 -> 3 1 / T 7 4 1 -> 2 1 / OUT 123`; predicted: ``
- prompt: `case 32585. ADD2 75 + 79`; expected: `OP ADD / A 7 5 / B 7 9 / U 5 9 0 -> 4 1 / T 7 7 1 -> 5 1 / OUT 154`; predicted: `OP ADD / A 4 9 / B 5 7710 / U 9 6 0 -> 7 1 / T 4 5 1 -> 0 1 / OUT 107`
### sub_2digit_no_borrow

- prompt: `case 45169. SUB2 66 - 66`; expected: `OP SUB / A 6 6 / B 6 6 / U 6 6 0 -> 0 0 / T 6 6 0 -> 0 0 / OUT 0`; predicted: `2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 2810 / U 8 0 0 -> 1 0 / T 2 0 -> 1 0 / OUT 11`
- prompt: `case 14741. SUB2 68 - 33`; expected: `OP SUB / A 6 8 / B 3 3 / U 8 3 0 -> 5 0 / T 6 3 0 -> 3 0 / OUT 35`; predicted: `OP SUB / A 2 8 / B 3 3 / U 8 3 0 -> 1 0 / T 2 3 0 -> 1 0 / OUT 11`
### sub_2digit_with_borrow

- prompt: `case 42767. SUB2 63 - 28`; expected: `OP SUB / A 6 3 / B 2 8 / U 3 8 0 -> 5 1 / T 6 2 1 -> 3 0 / OUT 35`; predicted: `OP SUB / A 3 4 / B 2 8 / U 4 8 0 -> 6 1 / T 3 2 1 -> 0 0 / OUT 6`
- prompt: `case 48824. SUB2 61 - 22`; expected: `OP SUB / A 6 1 / B 2 2 / U 1 2 0 -> 9 1 / T 6 2 1 -> 3 0 / OUT 39`; predicted: `OP SUB / A 4 1 / B 2 2 / U 1 2 0 -> 9 1 / T 4 2 1 -> 1 0 / OUT 19`
### missing_addend_simple

- prompt: `case 41359. MISSING_ADDEND known=54 target=94`; expected: `OP MISS_ADD / TARGET 9 4 / KNOWN 5 4 / U 4 4 0 -> 0 0 / T 9 5 0 -> 4 0 / OUT 40`; predicted: `OP MIS_ADDD / TARGET 0 4 / OWNOWN 5 0 9 0 4 0 -> 9 1 1 / T 9 5 1 0 0 / OUT 9`
- prompt: `case 35384. MISSING_ADDEND known=40 target=75`; expected: `OP MISS_ADD / TARGET 7 5 / KNOWN 4 0 / U 5 0 0 -> 5 0 / T 7 4 0 -> 3 0 / OUT 35`; predicted: `OP MISS_ADD / TARGET 7 5 / KNOWN 4 0 / U 5 0 0 -> 6 0 / T 7 4 0 -> 3 0 / OUT 36`
### compare_sum_simple

- prompt: `case 22095. COMPARE_SUM 55 + 43 vs 59 + 29`; expected: `OP COMPARE_SUM / L_A 5 5 / L_B 4 3 / L_U 5 3 0 -> 8 0 / L_T 5 4 0 -> 9 0 / L_OUT 98 / R_A 5 9 / R_B 2 9 / R_U 9 9 0 -> 8 1 / R_T 5 2 1 -> 8 0 / R_OUT 88 / CMP 98 > 88 / OUT 98`; predicted: `OP COMPARE_SUM / L_A 5 / L_B 4 3 / L_U 6 3 0 -> 8 0 / L_T 0 4 0 -> 5 0 / L_OUT 58 / R_A 2 7 / R_B 2 9 / R_U 7 9 0 -> 1 1 / R_T 2 2 1 -> 5 0 / R_OUT 51 / CMP 58 > 51 / OUT 58`
- prompt: `case 43883. COMPARE_SUM 35 + 60 vs 39 + 70`; expected: `OP COMPARE_SUM / L_A 3 5 / L_B 6 0 / L_U 5 0 0 -> 5 0 / L_T 3 6 0 -> 9 0 / L_OUT 95 / R_A 3 9 / R_B 7 0 / R_U 9 0 0 -> 9 0 / R_T 3 7 0 -> 0 1 / R_OUT 109 / CMP 95 < 109 / OUT 109`; predicted: `OP COMPARE_SUM / L_A 3 6 / L_B 4 7 / L_U 6 7 0 -> 8 0 / L_T 3 4 0 -> 7 0 / L_OUT 78 / R_A 3 9 / R_B 2 4 / R_U 9 4 0 -> 6 1 / R_T 3 2 1 -> 6 0 / R_OUT 66 / CMP 78 > 66 / OUT 78`
### double_step_simple

- prompt: `case 26783. DOUBLE_STEP 75 + 12 - 35`; expected: `OP DOUBLE / A 7 5 / B 1 2 / M_U 5 2 0 -> 7 0 / M_T 7 1 0 -> 8 0 / MID 87 / C 3 5 / O_U 7 5 0 -> 2 0 / O_T 8 3 0 -> 5 0 / OUT 52`; predicted: `9953 9953 1 5 1 1 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 3347 0 / MID`
- prompt: `case 27465. DOUBLE_STEP 42 + 13 - 10`; expected: `OP DOUBLE / A 4 2 / B 1 3 / M_U 2 3 0 -> 5 0 / M_T 4 1 0 -> 5 0 / MID 55 / C 1 0 / O_U 5 0 0 -> 5 0 / O_T 5 1 0 -> 4 0 / OUT 45`; predicted: `OP DOUBLE / A 4 2 / B 1 3 / M_U 2 3 0 -> 5 0 / M_T 4 1 0 -> 5 0 / MID 55 / C 1 0 / O_U 5 0 0 -> 4 0 / O_T 5 1 0 -> 4 0 / OUT 44`

## Conclusion

- Basic digit operations are already weak: `digit_add_carry` reaches only 0.446 same / 0.122 digit-holdout, and `digit_sub_borrow` reaches 0.144 same / 0.000 digit-holdout. This means the model has not learned the complete digit operation table under this compact symbolic prompt.
- Two-digit no-carry/no-borrow tasks memorize the same-range procedure well (`1.000` same), but collapse on unseen digit combinations and degrade on shifted/far ranges. That is range/table patching, not digit-rule transfer.
- Carry/borrow versions also learn same-range well, but are more brittle under shifted/far and show empty generations more often. Carry/borrow propagation is a separate failure on top of weak digit primitives.
- `missing_addend_simple` is poor even same-range, so treating missing addend as subtraction is not currently learned by this tiny setup.
- `compare_sum_simple` remains near-zero after raising `max_new_tokens` to 160. It fails both arithmetic substeps and comparison composition.
- `double_step_simple` is surprisingly better than compare/missing on same and shifted-in, but still collapses on digit-combo holdout. Multi-step state composition is partially learnable only when digit combinations are familiar.

## Recommendation

Next step should be an explicit digit-table curriculum before returning to broad arithmetic:

1. Train/eval `digit_add_carry` and `digit_sub_borrow` until same and digit-holdout are high.
2. Then add two-digit no-carry/no-borrow composition.
3. Then introduce carry/borrow propagation with explicit carry-state balancing.
4. Only after those pass, rebuild `missing_addend`, `compare_sum`, and `double_step` from the primitive curriculum.

Do not move to embeddings or larger models before this smaller benchmark is passing enough to tell architecture from data failure.




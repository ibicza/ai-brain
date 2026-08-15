# M-16.1 Addition Forensics Report

## Checks

- Commands: `uv run ruff format src tests`, `uv run ruff check src tests`, `uv run pytest -q`.
- Commit hash: `57ac66a`.
- Device: `device: cuda:0 / name: NVIDIA GeForce RTX 3050 Laptop GPU / cuda_available: True / cuda_device_count: 1 / total_memory_gb: 4.00 / compute_capability: 8.6`.

## Dataset And Length Distribution

| Split | Operation | Total | 1 Digit | 2 Digit | 3 Digit |
|---|---|---:|---:|---:|---:|
| far | addition | 995 | 0 / 0.0000 | 0 / 0.0000 | 995 / 1.0000 |
| far | subtraction | 1005 | 397 / 0.3950 | 608 / 0.6050 | 0 / 0.0000 |
| holdout | addition | 1030 | 0 / 0.0000 | 475 / 0.4612 | 555 / 0.5388 |
| holdout | subtraction | 970 | 264 / 0.2722 | 706 / 0.7278 | 0 / 0.0000 |
| same | addition | 981 | 0 / 0.0000 | 925 / 0.9429 | 56 / 0.0571 |
| same | subtraction | 1019 | 343 / 0.3366 | 676 / 0.6634 | 0 / 0.0000 |
| train | addition | 4006 | 0 / 0.0000 | 3787 / 0.9453 | 219 / 0.0547 |
| train | subtraction | 3994 | 1314 / 0.3290 | 2680 / 0.6710 | 0 / 0.0000 |

## M-16 Digit-Safe Baseline Diagnostics

### Addition Buckets

| Split | Bucket | Count | Final NEM | Digit Acc | U | T | H | State Acc | U Row | T Row | OUT |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| same | all | 981 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | carry | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | no_carry | 581 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | overflow_to_new_digit | 56 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | result_2digit | 925 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | result_3digit | 56 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | seen_digit_combo | 981 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | units_carry_only | 344 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| holdout | all | 1030 | 0.0000 | 0.2639 | 0.4359 | 0.1709 | 0.1171 | 0.7117 | 0.4359 | 0.1631 | 0.0000 |
| holdout | carry | 832 | 0.0000 | 0.2456 | 0.4567 | 0.1202 | 0.1171 | 0.6430 | 0.4567 | 0.1106 | 0.0000 |
| holdout | no_carry | 198 | 0.0000 | 0.3662 | 0.3485 | 0.3838 | n/a | 1.0000 | 0.3485 | 0.3838 | 0.0000 |
| holdout | overflow_to_new_digit | 555 | 0.0000 | 0.2108 | 0.4775 | 0.0378 | 0.1171 | 0.5063 | 0.4775 | 0.0288 | 0.0000 |
| holdout | result_2digit | 475 | 0.0000 | 0.3568 | 0.3874 | 0.3263 | n/a | 0.9516 | 0.3874 | 0.3200 | 0.0000 |
| holdout | result_3digit | 555 | 0.0000 | 0.2108 | 0.4775 | 0.0378 | 0.1171 | 0.5063 | 0.4775 | 0.0288 | 0.0000 |
| holdout | units_carry_only | 277 | 0.0000 | 0.3502 | 0.4152 | 0.2852 | n/a | 0.9170 | 0.4152 | 0.2744 | 0.0000 |
| holdout | unseen_digit_combo | 1030 | 0.0000 | 0.2639 | 0.4359 | 0.1709 | 0.1171 | 0.7117 | 0.4359 | 0.1631 | 0.0000 |
| far | all | 995 | 0.0000 | 0.4117 | 1.0000 | 0.1869 | 0.0482 | 0.5241 | 1.0000 | 0.0000 | 0.0000 |
| far | carry | 995 | 0.0000 | 0.4117 | 1.0000 | 0.1869 | 0.0482 | 0.5241 | 1.0000 | 0.0000 | 0.0000 |
| far | overflow_to_new_digit | 995 | 0.0000 | 0.4117 | 1.0000 | 0.1869 | 0.0482 | 0.5241 | 1.0000 | 0.0000 | 0.0000 |
| far | result_3digit | 995 | 0.0000 | 0.4117 | 1.0000 | 0.1869 | 0.0482 | 0.5241 | 1.0000 | 0.0000 | 0.0000 |
| far | seen_digit_combo | 597 | 0.0000 | 0.3825 | 1.0000 | 0.1474 | 0.0000 | 0.5000 | 1.0000 | 0.0000 | 0.0000 |
| far | unseen_digit_combo | 398 | 0.0000 | 0.4556 | 1.0000 | 0.2462 | 0.1206 | 0.5603 | 1.0000 | 0.0000 | 0.0000 |

### Subtraction Buckets

| Split | Bucket | Count | Final NEM | Digit Acc | U | T | H | State Acc | U Row | T Row | OUT |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| same | all | 1019 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | borrow | 350 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | no_borrow | 669 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | result_1digit | 343 | 1.0000 | 1.0000 | 1.0000 | n/a | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | result_2digit | 676 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| same | seen_digit_combo | 1019 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | n/a | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| holdout | all | 970 | 0.1082 | 0.4135 | 0.5309 | 0.2521 | n/a | 0.9031 | 0.5289 | 0.2320 | 0.1082 |
| holdout | borrow | 402 | 0.0124 | 0.3407 | 0.4925 | 0.1172 | n/a | 0.9428 | 0.4876 | 0.1741 | 0.0124 |
| holdout | no_borrow | 568 | 0.1761 | 0.4625 | 0.5581 | 0.3372 | n/a | 0.8750 | 0.5581 | 0.2729 | 0.1761 |
| holdout | result_1digit | 264 | 0.0644 | 0.5152 | 0.5152 | n/a | n/a | 0.9129 | 0.5152 | 0.2500 | 0.0644 |
| holdout | result_2digit | 706 | 0.1246 | 0.3945 | 0.5368 | 0.2521 | n/a | 0.8994 | 0.5340 | 0.2252 | 0.1246 |
| holdout | unseen_digit_combo | 970 | 0.1082 | 0.4135 | 0.5309 | 0.2521 | n/a | 0.9031 | 0.5289 | 0.2320 | 0.1082 |
| far | all | 1005 | 0.3612 | 0.7985 | 0.9970 | 0.4704 | n/a | 0.9985 | 0.9990 | 0.0945 | 0.3612 |
| far | borrow | 305 | 0.5443 | 0.8547 | 1.0000 | 0.5705 | n/a | 1.0000 | 1.0000 | 0.1213 | 0.5443 |
| far | no_borrow | 700 | 0.2814 | 0.7760 | 0.9957 | 0.4358 | n/a | 0.9979 | 0.9986 | 0.0829 | 0.2814 |
| far | result_1digit | 397 | 0.1940 | 0.9924 | 0.9924 | n/a | n/a | 0.9962 | 0.9975 | 0.0655 | 0.1940 |
| far | result_2digit | 608 | 0.4704 | 0.7352 | 1.0000 | 0.4704 | n/a | 1.0000 | 1.0000 | 0.1135 | 0.4704 |
| far | seen_digit_combo | 700 | 0.2814 | 0.7760 | 0.9957 | 0.4358 | n/a | 0.9979 | 0.9986 | 0.0829 | 0.2814 |
| far | unseen_digit_combo | 305 | 0.5443 | 0.8547 | 1.0000 | 0.5705 | n/a | 1.0000 | 1.0000 | 0.1213 | 0.5443 |

## Tokenization Checks

| Text | Tokens | IDs | Offsets |
|---|---|---|---|
| `case 0. ADD2_COMPOSED 47 + 21` | `['case', 'Ġ', '0', '.', 'Ġ', 'A', 'D', 'D', '2', '_', 'C', 'O', 'M', 'P', 'O', 'S', 'E', 'D', 'Ġ', '4', '7', 'Ġ+', 'Ġ', '2', '1']` | `[305, 227, 22, 20, 227, 39, 42, 42, 24, 69, 41, 53, 51, 54, 53, 57, 43, 42, 227, 26, 29, 491, 227, 24, 23]` | `[[0, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11], [11, 12], [12, 13], [13, 14], [14, 15], [15, 16], [16, 17], [17, 18], [18, 19], [19, 20], [20, 21], [21, 22], [22, 23], [23, 24], [24, 26], [26, 27], [27, 28], [28, 29]]` |
| `OUT 68` | `['O', 'U', 'T', 'Ġ', '6', '8']` | `[53, 59, 58, 227, 28, 30]` | `[[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]` |
| `case 1. ADD2_COMPOSED 84 + 65` | `['case', 'Ġ', '1', '.', 'Ġ', 'A', 'D', 'D', '2', '_', 'C', 'O', 'M', 'P', 'O', 'S', 'E', 'D', 'Ġ', '8', '4', 'Ġ+', 'Ġ', '6', '5']` | `[305, 227, 23, 20, 227, 39, 42, 42, 24, 69, 41, 53, 51, 54, 53, 57, 43, 42, 227, 30, 26, 491, 227, 28, 27]` | `[[0, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11], [11, 12], [12, 13], [13, 14], [14, 15], [15, 16], [16, 17], [17, 18], [18, 19], [19, 20], [20, 21], [21, 22], [22, 23], [23, 24], [24, 26], [26, 27], [27, 28], [28, 29]]` |
| `OUT 149` | `['O', 'U', 'T', 'Ġ', '1', '4', '9']` | `[53, 59, 58, 227, 23, 26, 31]` | `[[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7]]` |
| `OUT_RTL 9 4 1
FINAL 149` | `['O', 'U', 'T', '_', 'R', 'T', 'L', 'Ġ', '9', 'Ġ', '4', 'Ġ', '1', 'Ċ', 'F', 'I', 'N', 'A', 'L', 'Ġ', '1', '4', '9']` | `[53, 59, 58, 69, 56, 58, 50, 227, 31, 227, 26, 227, 23, 205, 44, 47, 52, 39, 50, 227, 23, 26, 31]` | `[[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11], [11, 12], [12, 13], [13, 14], [14, 15], [15, 16], [16, 17], [17, 18], [18, 19], [19, 20], [20, 21], [21, 22], [22, 23]]` |

## Generated Answer Checks

| Source | Prompt | Expected Final | Predicted Final | Generated Answer |
|---|---|---:|---:|---|
| M-16 digit_safe same | `case 32393. ADD2_COMPOSED 47 + 21` | `68` | `68` | OP ADD<br>A 4 7<br>B 2 1<br>U 7 1 0 -> 8 0<br>T 4 2 0 -> 6 0<br>OUT 68 |
| M-16 digit_safe far | `case 31008. ADD2_COMPOSED 84 + 65` | `149` | `69` | OP ADD<br>A 8 4<br>B 6 5<br>U 4 5 0 -> 9 0<br>T 8 6 0 -> 6 0<br>OUT 69 |
| M-16.1 LSD trace same | `case 32393. ADD2_COMPOSED 47 + 21` | `68` | `68` | OP ADD_RTL<br>U 7 1 C0 -> 8 C0<br>T 4 2 C0 -> 6 C0<br>OUT_RTL 8 6<br>FINAL 68 |
| M-16.1 LSD trace far | `case 31008. ADD2_COMPOSED 84 + 65` | `149` | `49` | OP ADD_RTL<br>U 4 5 C0 -> 9 C0<br>T 1 6 C0 -> 4 C0<br>OUT_RTL 9 4<br>FINAL 49 |

## Position Checks

- Position Coupling source: [HanseulJo/position-coupling](https://github.com/HanseulJo/position-coupling), `src/data/addition.py`, `AdditionDatasetWithCoupledPositions`.
- Abacus source: [mcleish7/arithmetic](https://github.com/mcleish7/arithmetic), `abacus.py`, `Abacus.helper`.

### Position Coupling

| Example | Token | Our ID | Reference/Paper-Intended ID | Note |
|---|---|---:|---:|---|
| `47+21` | `0` | 1 | 1 | same significance should share this ID |
| `47+21` | `2` | 1 | 1 | same significance should share this ID |
| `47+21` | `4` | 2 | 2 | same significance should share this ID |
| `47+21` | `7` | 1 | 1 | same significance should share this ID |
| `47+21` | `2` | 2 | 2 | same significance should share this ID |
| `47+21` | `1` | 1 | 1 | same significance should share this ID |
| `47+21` | `6` | 2 | 2 | paper-equivalent only if output is LSD-first/reversed |
| `47+21` | `8` | 1 | 1 | paper-equivalent only if output is LSD-first/reversed |
| `84+65` | `1` | 1 | 1 | same significance should share this ID |
| `84+65` | `2` | 1 | 1 | same significance should share this ID |
| `84+65` | `8` | 2 | 2 | same significance should share this ID |
| `84+65` | `4` | 1 | 1 | same significance should share this ID |
| `84+65` | `6` | 2 | 2 | same significance should share this ID |
| `84+65` | `5` | 1 | 1 | same significance should share this ID |
| `84+65` | `1` | 3 | 3 | paper-equivalent only if output is LSD-first/reversed |
| `84+65` | `4` | 2 | 2 | paper-equivalent only if output is LSD-first/reversed |
| `84+65` | `9` | 1 | 1 | paper-equivalent only if output is LSD-first/reversed |
| `71+63` | `2` | 1 | 1 | same significance should share this ID |
| `71+63` | `2` | 1 | 1 | same significance should share this ID |
| `71+63` | `7` | 2 | 2 | same significance should share this ID |
| `71+63` | `1` | 1 | 1 | same significance should share this ID |
| `71+63` | `6` | 2 | 2 | same significance should share this ID |
| `71+63` | `3` | 1 | 1 | same significance should share this ID |
| `71+63` | `1` | 3 | 3 | paper-equivalent only if output is LSD-first/reversed |
| `71+63` | `3` | 2 | 2 | paper-equivalent only if output is LSD-first/reversed |
| `71+63` | `4` | 1 | 1 | paper-equivalent only if output is LSD-first/reversed |
| `20+55` | `3` | 1 | 1 | same significance should share this ID |
| `20+55` | `2` | 1 | 1 | same significance should share this ID |
| `20+55` | `2` | 2 | 2 | same significance should share this ID |
| `20+55` | `0` | 1 | 1 | same significance should share this ID |
| `20+55` | `5` | 2 | 2 | same significance should share this ID |
| `20+55` | `5` | 1 | 1 | same significance should share this ID |
| `20+55` | `7` | 2 | 2 | paper-equivalent only if output is LSD-first/reversed |
| `20+55` | `5` | 1 | 1 | paper-equivalent only if output is LSD-first/reversed |
| `58+47` | `4` | 1 | 1 | same significance should share this ID |
| `58+47` | `2` | 1 | 1 | same significance should share this ID |
| `58+47` | `5` | 2 | 2 | same significance should share this ID |
| `58+47` | `8` | 1 | 1 | same significance should share this ID |
| `58+47` | `4` | 2 | 2 | same significance should share this ID |
| `58+47` | `7` | 1 | 1 | same significance should share this ID |
| `58+47` | `1` | 3 | 3 | paper-equivalent only if output is LSD-first/reversed |
| `58+47` | `0` | 2 | 2 | paper-equivalent only if output is LSD-first/reversed |
| `58+47` | `5` | 1 | 1 | paper-equivalent only if output is LSD-first/reversed |

### Abacus

| Example | Token | Our ID | Reference/Paper-Intended ID | Note |
|---|---|---:|---:|---|
| `47+21` | `0` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `4` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `7` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `2` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `1` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `6` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `47+21` | `8` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `1` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `8` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `4` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `6` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `5` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `1` | 3 | 1 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `4` | 2 | 2 | official Abacus segment-start; paper requires reversed integers |
| `84+65` | `9` | 1 | 3 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `7` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `1` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `6` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `3` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `1` | 3 | 1 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `3` | 2 | 2 | official Abacus segment-start; paper requires reversed integers |
| `71+63` | `4` | 1 | 3 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `3` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `2` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `0` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `5` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `5` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `7` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `20+55` | `5` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `4` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `2` | 1 | 1 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `5` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `8` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `4` | 2 | 1 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `7` | 1 | 2 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `1` | 3 | 1 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `0` | 2 | 2 | official Abacus segment-start; paper requires reversed integers |
| `58+47` | `5` | 1 | 3 | official Abacus segment-start; paper requires reversed integers |

## Addition-Only Ablation

| Variant | Seed | Addition No-Carry | Addition Carry | Addition Overflow | Addition Holdout | Addition Far | Subtraction Holdout | Subtraction Far |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a_digit_safe_normal | 310161 | 0.9845 | 0.8800 | 0.8571 | 0.0000 | 0.0000 | 0.0021 | 0.0000 |
| b_digit_safe_rtl | 310161 | 0.1893 | 0.0625 | 0.0536 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| c_digit_safe_lsd_trace | 310161 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0093 | 0.0000 |
| c_digit_safe_lsd_trace | 310162 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0082 | 0.0000 |
| c_digit_safe_lsd_trace | 310163 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| d_abacus_lsd_trace | 310161 | 0.8761 | 0.9650 | 0.9464 | 0.0000 | 0.0000 | 0.0062 | 0.0149 |

## Mean / Std

| Variant | Metric | Mean | Std | N |
|---|---|---:|---:|---:|
| a_digit_safe_normal | addition_no_carry | 0.9845 | 0.0000 | 1 |
| a_digit_safe_normal | addition_carry | 0.8800 | 0.0000 | 1 |
| a_digit_safe_normal | addition_overflow_to_new_digit | 0.8571 | 0.0000 | 1 |
| a_digit_safe_normal | addition_holdout | 0.0000 | 0.0000 | 1 |
| a_digit_safe_normal | addition_far | 0.0000 | 0.0000 | 1 |
| a_digit_safe_normal | subtraction_holdout | 0.0021 | 0.0000 | 1 |
| a_digit_safe_normal | subtraction_far | 0.0000 | 0.0000 | 1 |
| b_digit_safe_rtl | addition_no_carry | 0.1893 | 0.0000 | 1 |
| b_digit_safe_rtl | addition_carry | 0.0625 | 0.0000 | 1 |
| b_digit_safe_rtl | addition_overflow_to_new_digit | 0.0536 | 0.0000 | 1 |
| b_digit_safe_rtl | addition_holdout | 0.0000 | 0.0000 | 1 |
| b_digit_safe_rtl | addition_far | 0.0000 | 0.0000 | 1 |
| b_digit_safe_rtl | subtraction_holdout | 0.0000 | 0.0000 | 1 |
| b_digit_safe_rtl | subtraction_far | 0.0000 | 0.0000 | 1 |
| c_digit_safe_lsd_trace | addition_no_carry | 1.0000 | 0.0000 | 3 |
| c_digit_safe_lsd_trace | addition_carry | 1.0000 | 0.0000 | 3 |
| c_digit_safe_lsd_trace | addition_overflow_to_new_digit | 1.0000 | 0.0000 | 3 |
| c_digit_safe_lsd_trace | addition_holdout | 0.0000 | 0.0000 | 3 |
| c_digit_safe_lsd_trace | addition_far | 0.0000 | 0.0000 | 3 |
| c_digit_safe_lsd_trace | subtraction_holdout | 0.0058 | 0.0042 | 3 |
| c_digit_safe_lsd_trace | subtraction_far | 0.0000 | 0.0000 | 3 |
| d_abacus_lsd_trace | addition_no_carry | 0.8761 | 0.0000 | 1 |
| d_abacus_lsd_trace | addition_carry | 0.9650 | 0.0000 | 1 |
| d_abacus_lsd_trace | addition_overflow_to_new_digit | 0.9464 | 0.0000 | 1 |
| d_abacus_lsd_trace | addition_holdout | 0.0000 | 0.0000 | 1 |
| d_abacus_lsd_trace | addition_far | 0.0000 | 0.0000 | 1 |
| d_abacus_lsd_trace | subtraction_holdout | 0.0062 | 0.0000 | 1 |
| d_abacus_lsd_trace | subtraction_far | 0.0149 | 0.0000 | 1 |

## Interpretation

- M-16 digit-safe addition failures are not final-string-only failures when carry is involved: trace rows show the model often gets U correct, then loses the T carry/overflow state and emits a 2-digit OUT.
- The strongest distribution mismatch is output length: train addition has 5.47% 3-digit results, same eval has 5.71%, holdout has 53.88%, and far has 100%. This explains why same-range overflow can be memorized while shifted/far overflow collapses.
- Official Position Coupling trains with reversed output (`reverse_output: True`) and assigns increasing positions to the LSD-first label. Our M-16 coupled feature assigned significance IDs inside normal-order text, but did not force the supervised output order to be LSD-first.
- Official Abacus assigns positions from the start of each consecutive digit span and explicitly requires reversed integers. Our M-16 Abacus feature used right-aligned normal-order spans, so it was significance-like but not the paper formulation.
- Addition-only ablation confirms the anomaly: `compact_lsd_trace` reaches 1.0000 on same-range no-carry/carry/overflow for 3/3 seeds, but remains 0.0000 on holdout and far. So the failure is not only output order or final-answer extraction; it is unseen digit-combo/range transfer under output-length shift.
- Next step should not be recurrent/FoNE/xVal yet. The cleanest next diagnostic is balanced 3-digit-overflow and held-out-combo training for addition, with explicit carry-state coverage separated from output-length growth.

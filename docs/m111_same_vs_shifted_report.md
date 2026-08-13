# M-11.1 Same-Range vs Shifted-Range Report

## Checks

- `uv run ruff format src tests`: passed, 50 files left unchanged
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: 129 passed
- Source HEAD before M-11.1 commit: `cd6e9930c88fc9e6205e69bab030eed914cdc1c0`
- Device: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`)

## Dataset Verification

| dataset | preset | format | profiles | counts | ranges | intersections | sorting lengths |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m111_quantity_direct_normal | quantity_direct | normal_answer | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=10000, same=1000, shifted=1000 | {"train_same": [1, 30], "eval_same": [1, 30], "eval_shifted": [21, 100]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_quantity_direct_digit_spaced | quantity_direct | digit_spaced | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=10000, same=1000, shifted=1000 | {"train_same": [1, 30], "eval_same": [1, 30], "eval_shifted": [21, 100]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_quantity_direct_canonical | quantity_direct | canonical_numeric | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=10000, same=1000, shifted=1000 | {"train_same": [1, 30], "eval_same": [1, 30], "eval_shifted": [21, 100]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_arithmetic_normal | arithmetic | normal_answer | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=20000, same=2000, shifted=2000 | {"train_same": [0, 50], "eval_same": [0, 50], "eval_shifted": [0, 117]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_arithmetic_scratchpad | arithmetic | scratchpad | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=20000, same=2000, shifted=2000 | {"train_same": [0, 50], "eval_same": [0, 50], "eval_shifted": [0, 117]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_arithmetic_canonical | arithmetic | canonical_numeric | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=20000, same=2000, shifted=2000 | {"train_same": [0, 50], "eval_same": [0, 50], "eval_shifted": [0, 117]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_state_change_normal | state_change | normal_answer | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=15000, same=1500, shifted=1500 | {"train_same": [0, 30], "eval_same": [0, 30], "eval_shifted": [1, 100]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_state_change_canonical | state_change | canonical_numeric | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=15000, same=1500, shifted=1500 | {"train_same": [0, 30], "eval_same": [0, 30], "eval_shifted": [1, 100]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | "" |
| m111_sorting_short_normal | sorting_short | normal_answer | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=10000, same=1000, shifted=1000 | {"train_same": [0, 49], "eval_same": [0, 49], "eval_shifted": [20, 119]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | {"train_same": [3, 4], "eval_same": [3, 4], "eval_shifted": [3, 4]} |
| m111_sorting_short_canonical | sorting_short | canonical_numeric | train_same=train_same, eval_same=eval_same, eval_shifted=eval_shifted | train=10000, same=1000, shifted=1000 | {"train_same": [0, 49], "eval_same": [0, 49], "eval_shifted": [20, 119]} | {"eval_same_shifted_intersection_count": 0, "train_eval_same_intersection_count": 0, "train_eval_shifted_intersection_count": 0} | {"train_same": [3, 4], "eval_same": [3, 4], "eval_shifted": [3, 4]} |

All datasets have zero prompt intersections across `train_same`, `eval_same`, and `eval_shifted`; all task types are present; all splits have zero duplicate prompts from `dataset-stats`. `eval_same` uses the same numeric ranges as `train_same`, while `eval_shifted` uses shifted numeric ranges. Sorting remains 3-4 numbers in every split.

## Training Runs

| preset | format | steps | checkpoint | final train loss | final eval_same loss | batch/OOM |
| --- | --- | --- | --- | --- | --- | --- |
| quantity_direct | normal_answer | 5000 | runs/m111_quantity_direct_normal_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 0.0000 | 8 / none |
| quantity_direct | digit_spaced | 5000 | runs/m111_quantity_direct_digit_spaced_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 0.0000 | 8 / none |
| quantity_direct | canonical_numeric | 5000 | runs/m111_quantity_direct_canonical_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 0.0000 | 8 / none |
| arithmetic | normal_answer | 10000 | runs/m111_arithmetic_normal_tiny_10k/checkpoints/step_010000.pt | 0.7590 | 0.8041 | 8 / none |
| arithmetic | scratchpad | 10000 | runs/m111_arithmetic_scratchpad_tiny_10k/checkpoints/step_010000.pt | 0.1660 | 0.1252 | 8 / none |
| arithmetic | canonical_numeric | 10000 | runs/m111_arithmetic_canonical_tiny_10k/checkpoints/step_010000.pt | 0.0559 | 0.0613 | 8 / none |
| state_change | normal_answer | 8000 | runs/m111_state_change_normal_tiny_8k/checkpoints/step_008000.pt | 0.3146 | 0.3122 | 8 / none |
| state_change | canonical_numeric | 8000 | runs/m111_state_change_canonical_tiny_8k/checkpoints/step_008000.pt | 0.0297 | 0.0264 | 8 / none |
| sorting_short | normal_answer | 8000 | runs/m111_sorting_short_normal_tiny_8k/checkpoints/step_008000.pt | 0.0850 | 0.1436 | 8 / none |
| sorting_short | canonical_numeric | 8000 | runs/m111_sorting_short_canonical_tiny_8k/checkpoints/step_008000.pt | 0.0249 | 0.0327 | 8 / none |

## Results Table

| preset | format | eval_same final NEM | eval_shifted final NEM | gap | interpretation |
| --- | --- | --- | --- | --- | --- |
| quantity_direct | normal_answer | 1.0000 | 0.3000 | 0.7000 | same high, shifted low => range/number representation failure |
| quantity_direct | digit_spaced | 1.0000 | 0.3680 | 0.6320 | same high, shifted low => range/number representation failure |
| quantity_direct | canonical_numeric | 1.0000 | 0.3720 | 0.6280 | same high, shifted low => range/number representation failure |
| arithmetic | normal_answer | 0.0795 | 0.0065 | 0.0730 | same low, shifted low => rule/capacity failure |
| arithmetic | scratchpad | 0.1620 | 0.0135 | 0.1485 | same low, shifted low => rule/capacity failure |
| arithmetic | canonical_numeric | 0.0580 | 0.0055 | 0.0525 | same low, shifted low => rule/capacity failure |
| state_change | normal_answer | 0.6200 | 0.2280 | 0.3920 | mixed => partial same-range generalization with transfer gap |
| state_change | canonical_numeric | 0.6080 | 0.2327 | 0.3753 | mixed => partial same-range generalization with transfer gap |
| sorting_short | normal_answer | 0.6790 | 0.0090 | 0.6700 | mixed => partial same-range generalization with transfer gap |
| sorting_short | canonical_numeric | 0.6530 | 0.0070 | 0.6460 | mixed => partial same-range generalization with transfer gap |

## Detailed Metrics

| preset | format | same full NEM | same final NEM | same empty | shifted full NEM | shifted final NEM | shifted empty | shifted avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quantity_direct | normal_answer | 1.0000 | 1.0000 | 0.0000 | 0.3000 | 0.3000 | 0.0890 | 2.8220 |
| quantity_direct | digit_spaced | 1.0000 | 1.0000 | 0.0000 | 0.3590 | 0.3680 | 0.1020 | 3.4650 |
| quantity_direct | canonical_numeric | 1.0000 | 1.0000 | 0.0000 | 0.3000 | 0.3720 | 0.0000 | 35.9060 |
| arithmetic | normal_answer | 0.0795 | 0.0795 | 0.0025 | 0.0065 | 0.0065 | 0.1025 | 3.0290 |
| arithmetic | scratchpad | 0.1525 | 0.1620 | 0.0000 | 0.0095 | 0.0135 | 0.0225 | 27.4035 |
| arithmetic | canonical_numeric | 0.0430 | 0.0580 | 0.0000 | 0.0015 | 0.0055 | 0.0000 | 83.2395 |
| state_change | normal_answer | 0.6200 | 0.6200 | 0.0000 | 0.2280 | 0.2280 | 0.0000 | 4.4653 |
| state_change | canonical_numeric | 0.4347 | 0.6080 | 0.0000 | 0.2147 | 0.2327 | 0.0000 | 57.9820 |
| sorting_short | normal_answer | 0.6790 | 0.6790 | 0.0000 | 0.0090 | 0.0090 | 0.0570 | 7.7580 |
| sorting_short | canonical_numeric | 0.5550 | 0.6530 | 0.0000 | 0.0050 | 0.0070 | 0.0000 | 69.4350 |

## By-Task Metrics

| preset | format | split | task_type | count | full NEM | final NEM | empty rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| quantity_direct | normal_answer | eval_same | quantity.direct | 331 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | normal_answer | eval_same | quantity.known_zero | 345 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | normal_answer | eval_same | quantity.location_direct | 324 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | normal_answer | eval_shifted | quantity.direct | 346 | 0.0983 | 0.0983 | 0.0000 |
| quantity_direct | normal_answer | eval_shifted | quantity.known_zero | 315 | 0.7175 | 0.7175 | 0.2825 |
| quantity_direct | normal_answer | eval_shifted | quantity.location_direct | 339 | 0.1180 | 0.1180 | 0.0000 |
| quantity_direct | digit_spaced | eval_same | quantity.direct | 325 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | digit_spaced | eval_same | quantity.known_zero | 339 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | digit_spaced | eval_same | quantity.location_direct | 336 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | digit_spaced | eval_shifted | quantity.direct | 345 | 0.1884 | 0.2029 | 0.0116 |
| quantity_direct | digit_spaced | eval_shifted | quantity.known_zero | 324 | 0.7068 | 0.7068 | 0.2932 |
| quantity_direct | digit_spaced | eval_shifted | quantity.location_direct | 331 | 0.1964 | 0.2085 | 0.0091 |
| quantity_direct | canonical_numeric | eval_same | quantity.direct | 331 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | canonical_numeric | eval_same | quantity.known_zero | 345 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | canonical_numeric | eval_same | quantity.location_direct | 324 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | canonical_numeric | eval_shifted | quantity.direct | 346 | 0.0983 | 0.0983 | 0.0000 |
| quantity_direct | canonical_numeric | eval_shifted | quantity.known_zero | 315 | 0.7175 | 0.9460 | 0.0000 |
| quantity_direct | canonical_numeric | eval_shifted | quantity.location_direct | 339 | 0.1180 | 0.1180 | 0.0000 |
| arithmetic | normal_answer | eval_same | arithmetic.add | 383 | 0.1097 | 0.1097 | 0.0000 |
| arithmetic | normal_answer | eval_same | arithmetic.compare_sum | 419 | 0.0907 | 0.0907 | 0.0024 |
| arithmetic | normal_answer | eval_same | arithmetic.double_step | 384 | 0.0677 | 0.0677 | 0.0000 |
| arithmetic | normal_answer | eval_same | arithmetic.missing_addend | 412 | 0.0631 | 0.0631 | 0.0097 |
| arithmetic | normal_answer | eval_same | arithmetic.subtract | 402 | 0.0672 | 0.0672 | 0.0000 |
| arithmetic | normal_answer | eval_shifted | arithmetic.add | 407 | 0.0049 | 0.0049 | 0.1400 |
| arithmetic | normal_answer | eval_shifted | arithmetic.compare_sum | 414 | 0.0000 | 0.0000 | 0.1643 |
| arithmetic | normal_answer | eval_shifted | arithmetic.double_step | 403 | 0.0099 | 0.0099 | 0.0868 |
| arithmetic | normal_answer | eval_shifted | arithmetic.missing_addend | 399 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | normal_answer | eval_shifted | arithmetic.subtract | 377 | 0.0186 | 0.0186 | 0.1194 |
| arithmetic | scratchpad | eval_same | arithmetic.add | 383 | 0.3943 | 0.4021 | 0.0000 |
| arithmetic | scratchpad | eval_same | arithmetic.compare_sum | 419 | 0.0692 | 0.0692 | 0.0000 |
| arithmetic | scratchpad | eval_same | arithmetic.double_step | 384 | 0.0312 | 0.0677 | 0.0000 |
| arithmetic | scratchpad | eval_same | arithmetic.missing_addend | 412 | 0.0485 | 0.0510 | 0.0000 |
| arithmetic | scratchpad | eval_same | arithmetic.subtract | 402 | 0.2313 | 0.2338 | 0.0000 |
| arithmetic | scratchpad | eval_shifted | arithmetic.add | 407 | 0.0049 | 0.0049 | 0.0000 |
| arithmetic | scratchpad | eval_shifted | arithmetic.compare_sum | 414 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | scratchpad | eval_shifted | arithmetic.double_step | 403 | 0.0000 | 0.0074 | 0.0000 |
| arithmetic | scratchpad | eval_shifted | arithmetic.missing_addend | 399 | 0.0000 | 0.0075 | 0.1103 |
| arithmetic | scratchpad | eval_shifted | arithmetic.subtract | 377 | 0.0451 | 0.0504 | 0.0027 |
| arithmetic | canonical_numeric | eval_same | arithmetic.add | 383 | 0.0888 | 0.0914 | 0.0000 |
| arithmetic | canonical_numeric | eval_same | arithmetic.compare_sum | 419 | 0.0000 | 0.0048 | 0.0000 |
| arithmetic | canonical_numeric | eval_same | arithmetic.double_step | 384 | 0.0000 | 0.0547 | 0.0000 |
| arithmetic | canonical_numeric | eval_same | arithmetic.missing_addend | 412 | 0.0558 | 0.0655 | 0.0000 |
| arithmetic | canonical_numeric | eval_same | arithmetic.subtract | 402 | 0.0721 | 0.0771 | 0.0000 |
| arithmetic | canonical_numeric | eval_shifted | arithmetic.add | 407 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | canonical_numeric | eval_shifted | arithmetic.compare_sum | 414 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | canonical_numeric | eval_shifted | arithmetic.double_step | 403 | 0.0000 | 0.0124 | 0.0000 |
| arithmetic | canonical_numeric | eval_shifted | arithmetic.missing_addend | 399 | 0.0000 | 0.0025 | 0.0000 |
| arithmetic | canonical_numeric | eval_shifted | arithmetic.subtract | 377 | 0.0080 | 0.0133 | 0.0000 |
| state_change | normal_answer | eval_same | state_change.add | 320 | 0.0469 | 0.0469 | 0.0000 |
| state_change | normal_answer | eval_same | state_change.insufficient_start | 289 | 1.0000 | 1.0000 | 0.0000 |
| state_change | normal_answer | eval_same | state_change.other_object_no_change | 310 | 0.9000 | 0.9000 | 0.0000 |
| state_change | normal_answer | eval_same | state_change.other_subject_no_change | 260 | 0.9231 | 0.9231 | 0.0000 |
| state_change | normal_answer | eval_same | state_change.subtract | 321 | 0.3333 | 0.3333 | 0.0000 |
| state_change | normal_answer | eval_shifted | state_change.add | 314 | 0.0000 | 0.0000 | 0.0000 |
| state_change | normal_answer | eval_shifted | state_change.insufficient_start | 277 | 0.9675 | 0.9675 | 0.0000 |
| state_change | normal_answer | eval_shifted | state_change.other_object_no_change | 303 | 0.1287 | 0.1287 | 0.0000 |
| state_change | normal_answer | eval_shifted | state_change.other_subject_no_change | 268 | 0.0970 | 0.0970 | 0.0000 |
| state_change | normal_answer | eval_shifted | state_change.subtract | 338 | 0.0266 | 0.0266 | 0.0000 |
| state_change | canonical_numeric | eval_same | state_change.add | 320 | 0.0031 | 0.0031 | 0.0000 |
| state_change | canonical_numeric | eval_same | state_change.insufficient_start | 289 | 1.0000 | 1.0000 | 0.0000 |
| state_change | canonical_numeric | eval_same | state_change.other_object_no_change | 310 | 1.0000 | 1.0000 | 0.0000 |
| state_change | canonical_numeric | eval_same | state_change.other_subject_no_change | 260 | 0.0000 | 1.0000 | 0.0000 |
| state_change | canonical_numeric | eval_same | state_change.subtract | 321 | 0.1620 | 0.1620 | 0.0000 |
| state_change | canonical_numeric | eval_shifted | state_change.add | 314 | 0.0000 | 0.0000 | 0.0000 |
| state_change | canonical_numeric | eval_shifted | state_change.insufficient_start | 277 | 1.0000 | 1.0000 | 0.0000 |
| state_change | canonical_numeric | eval_shifted | state_change.other_object_no_change | 303 | 0.1287 | 0.1287 | 0.0000 |
| state_change | canonical_numeric | eval_shifted | state_change.other_subject_no_change | 268 | 0.0000 | 0.0970 | 0.0000 |
| state_change | canonical_numeric | eval_shifted | state_change.subtract | 338 | 0.0178 | 0.0207 | 0.0000 |
| sorting_short | normal_answer | eval_same | sorting.ascending | 505 | 0.6832 | 0.6832 | 0.0000 |
| sorting_short | normal_answer | eval_same | sorting.descending | 495 | 0.6747 | 0.6747 | 0.0000 |
| sorting_short | normal_answer | eval_shifted | sorting.ascending | 504 | 0.0079 | 0.0079 | 0.0536 |
| sorting_short | normal_answer | eval_shifted | sorting.descending | 496 | 0.0101 | 0.0101 | 0.0605 |
| sorting_short | canonical_numeric | eval_same | sorting.ascending | 505 | 0.5663 | 0.6792 | 0.0000 |
| sorting_short | canonical_numeric | eval_same | sorting.descending | 495 | 0.5434 | 0.6263 | 0.0000 |
| sorting_short | canonical_numeric | eval_shifted | sorting.ascending | 504 | 0.0060 | 0.0079 | 0.0000 |
| sorting_short | canonical_numeric | eval_shifted | sorting.descending | 496 | 0.0040 | 0.0060 | 0.0000 |

## Interpretation

- `quantity_direct`: Same-range is solved for all tested formats (1.0000), shifted-range falls to 0.3000-0.3720. This is a clear range/number representation failure, not a copy-rule failure.
- `arithmetic`: Same-range is still low (best scratchpad final NEM 0.1620), and shifted is near zero. This points to rule/capacity failure in addition to range transfer failure.
- `state_change`: Same-range is moderate/high around 0.6080-0.6200, shifted drops to about 0.2280-0.2327. This is partial same-range generalization with a strong transfer gap.
- `sorting_short`: Same-range is strong-ish (0.6530-0.6790), shifted collapses to 0.0070-0.0090. This is a strong range/number representation failure for sorting.

Overall, M-11.1 cleanly separates same-range and shifted-range behavior. Quantity, state_change, and sorting can generalize to unseen prompts inside the same numeric range, but fail badly when numbers shift. Arithmetic is weaker: even same-range eval remains low, especially for normal and canonical formats, so arithmetic needs both better procedural learning and better numeric representation.

## Recommendation

1. Prioritize digit/place/role embeddings or a digit-level tokenizer. The same-vs-shifted gap is too large to explain as prompt memorization alone.
2. Keep same-range vs shifted-range eval as a standard diagnostic for every future numeric representation change.
3. For arithmetic, add a stronger curriculum or smaller primitive decomposition before architecture changes, because same-range arithmetic is not solved yet.
4. Revisit architecture only after representation work and a curriculum pass; M-11.1 shows the main failure is numeric range transfer for quantity/sorting/state and rule learning for arithmetic.


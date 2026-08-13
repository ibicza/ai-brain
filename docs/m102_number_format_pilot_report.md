# M-10.2 Number Format + Scratchpad Pilot Report

## Checks

- `uv run ruff format src tests`: passed
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: 107 passed
- Source HEAD before M-10.2 commit: `f5044bdaa3cffbc3c33786d5cc0168b2a6d9ec6b`
- Device for training/eval: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`)

## Dataset Verification

| dataset | answer_format | train | eval | train dup | eval dup | task_types | sorting len |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m102_arithmetic_normal | normal_answer | 20000 | 2000 | 0 | 0 | arithmetic.add, arithmetic.subtract, arithmetic.missing_addend, arithmetic.double_step, arithmetic.compare_sum |  |
| m102_arithmetic_digit_spaced | digit_spaced | 20000 | 2000 | 0 | 0 | arithmetic.add, arithmetic.subtract, arithmetic.missing_addend, arithmetic.double_step, arithmetic.compare_sum |  |
| m102_arithmetic_scratchpad | scratchpad | 20000 | 2000 | 0 | 0 | arithmetic.add, arithmetic.subtract, arithmetic.missing_addend, arithmetic.double_step, arithmetic.compare_sum |  |
| m102_arithmetic_reversed | reversed_answer | 20000 | 2000 | 0 | 0 | arithmetic.add, arithmetic.subtract, arithmetic.missing_addend, arithmetic.double_step, arithmetic.compare_sum |  |
| m102_sorting_short_normal | normal_answer | 10000 | 1000 | 0 | 0 | sorting.ascending, sorting.descending | train 3-4, eval 3-4 |
| m102_sorting_short_digit_spaced | digit_spaced | 10000 | 1000 | 0 | 0 | sorting.ascending, sorting.descending | train 3-4, eval 3-4 |
| m102_sorting_short_scratchpad | scratchpad | 10000 | 1000 | 0 | 0 | sorting.ascending, sorting.descending | train 3-4, eval 3-4 |
| m102_state_change_normal | normal_answer | 15000 | 1500 | 0 | 0 | state_change.add, state_change.subtract, state_change.other_subject_no_change, state_change.other_object_no_change, state_change.insufficient_start |  |
| m102_state_change_scratchpad | scratchpad | 15000 | 1500 | 0 | 0 | state_change.add, state_change.subtract, state_change.other_subject_no_change, state_change.other_object_no_change, state_change.insufficient_start |  |
| m102_quantity_direct_normal | normal_answer | 10000 | 1000 | 0 | 0 | quantity.direct, quantity.location_direct, quantity.known_zero |  |
| m102_quantity_direct_digit_spaced | digit_spaced | 10000 | 1000 | 0 | 0 | quantity.direct, quantity.location_direct, quantity.known_zero |  |

All manifests had `quality_checks.no_prompt_intersection=true` and `quality_checks.all_task_types_present=true`. Transformed formats had `metadata.answer_format`, `metadata.original_prompt`, and `metadata.original_answer`; scratchpad answers were non-empty. Sorting short stayed at 3-4 numbers in both train and eval.

### Sample Formatted Examples

`arithmetic_scratchpad`

- arithmetic.double_step | prompt: case 6519. Сначала было 5. Добавили 7, затем убрали 4. Сколько осталось? | answer: step 1: 5 + 7 = 12
step 2: 12 - 4 = 8
answer: 8
- arithmetic.missing_addend | prompt: case 891. До 16 не хватает сколько, если уже есть 3? | answer: known: 3
target: 16
missing: 16 - 3 = 13
answer: 13
- arithmetic.add | prompt: case 6019. Найди сумму чисел 10 и 21. | answer: ones: 0 + 1 = 1
tens: 1 + 2 = 3
answer: 31

`sorting_scratchpad`

- sorting.descending | prompt: case 2682. Запиши числа от большего к меньшему: 21, 16, 29. | answer: numbers: 21, 16, 29
step 1: largest is 29
remaining: 21, 16
step 2: largest is 21
remaining: 16
step 3: largest is 16
answer: 29, 21, 16
- sorting.ascending | prompt: case 4964. Упорядочь числа по возрастанию: 18, 2, 16. | answer: numbers: 18, 2, 16
step 1: smallest is 2
remaining: 18, 16
step 2: smallest is 16
remaining: 18
step 3: smallest is 18
answer: 2, 16, 18
- sorting.ascending | prompt: case 7669. Упорядочь числа по возрастанию: 46, 21, 19. | answer: numbers: 46, 21, 19
step 1: smallest is 19
remaining: 46, 21
step 2: smallest is 21
remaining: 46
step 3: smallest is 46
answer: 19, 21, 46

`state_change_scratchpad`

- state_change.subtract | prompt: У Коли было 26 монет. У Коли забрали 22 монеты. Сколько монет осталось у Коли? | answer: start: 26
change: -22
ones: 6 - 2 = 4
tens: 2 - 2 = 0
answer: 4
- state_change.other_subject_no_change | prompt: У Саши было 24 печенья. Олегу дали ещё 9 печений. Сколько печений стало у Саши? | answer: given: 24
answer: 24
- state_change.add | prompt: У Веры было 2 мороженых. Вере дали ещё 14 мороженых. Сколько мороженых стало у Веры? | answer: start: 2
change: +14
ones: 2 + 4 = 6
tens: 0 + 1 = 1
answer: 16

`arithmetic_digit_spaced`

- arithmetic.double_step | prompt: case 6519. Сначала было 5. Добавили 7, затем убрали 4. Сколько осталось? | answer: 8
- arithmetic.missing_addend | prompt: case 891. До 1 6 не хватает сколько, если уже есть 3? | answer: 1 3
- arithmetic.add | prompt: case 7567. Сколько будет 0 + 2 2? | answer: 2 2

## Training Runs

| dataset | answer_format | steps | checkpoint | final train loss | final eval loss | batch/OOM |
| --- | --- | --- | --- | --- | --- | --- |
| arithmetic | normal_answer | 10000 | runs/m102_arithmetic_normal_tiny_10k/checkpoints/step_010000.pt | 0.7799 | 5.6614 | 8 / none |
| arithmetic | digit_spaced | 10000 | runs/m102_arithmetic_digit_spaced_tiny_10k/checkpoints/step_010000.pt | 0.7021 | 2.8364 | 8 / none |
| arithmetic | scratchpad | 10000 | runs/m102_arithmetic_scratchpad_tiny_10k/checkpoints/step_010000.pt | 0.1375 | 3.6876 | 8 / none |
| arithmetic | reversed_answer | 10000 | runs/m102_arithmetic_reversed_tiny_10k/checkpoints/step_010000.pt | 0.5548 | 5.4574 | 8 / none |
| sorting_short | normal_answer | 8000 | runs/m102_sorting_short_normal_tiny_8k/checkpoints/step_008000.pt | 0.0556 | 12.3526 | 8 / none |
| sorting_short | digit_spaced | 8000 | runs/m102_sorting_short_digit_spaced_tiny_8k/checkpoints/step_008000.pt | 0.0214 | 11.1117 | 8 / none |
| sorting_short | scratchpad | 8000 | runs/m102_sorting_short_scratchpad_tiny_8k/checkpoints/step_008000.pt | 0.0098 | 3.6387 | 8 / none |
| state_change | normal_answer | 8000 | runs/m102_state_change_normal_tiny_8k/checkpoints/step_008000.pt | 0.4247 | 4.0434 | 8 / none |
| state_change | scratchpad | 8000 | runs/m102_state_change_scratchpad_tiny_8k/checkpoints/step_008000.pt | 0.0217 | 2.5468 | 8 / none |
| quantity_direct | normal_answer | 5000 | runs/m102_quantity_direct_normal_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 5.5254 | 8 / none |
| quantity_direct | digit_spaced | 5000 | runs/m102_quantity_direct_digit_spaced_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 3.7436 | 8 / none |

## Eval Results

| preset | answer_format | NEM | false_answer_rate | empty_prediction_rate | avg_tokens_generated |
| --- | --- | --- | --- | --- | --- |
| arithmetic | normal_answer | 0.0080 | 0.0000 | 0.0755 | 2.8490 |
| arithmetic | digit_spaced | 0.0065 | 0.0000 | 0.0395 | 3.7605 |
| arithmetic | scratchpad | 0.0165 | 0.0000 | 0.0000 | 30.2940 |
| arithmetic | reversed_answer | 0.0090 | 0.0000 | 0.0540 | 3.7175 |
| sorting_short | normal_answer | 0.0140 | 0.0000 | 0.0630 | 7.6680 |
| sorting_short | digit_spaced | 0.0140 | 0.0000 | 0.2440 | 9.1180 |
| sorting_short | scratchpad | 0.0080 | 0.0000 | 0.0000 | 117.5880 |
| state_change | normal_answer | 0.2433 | 0.0000 | 0.0000 | 4.3867 |
| state_change | scratchpad | 0.2233 | 0.0000 | 0.0000 | 31.9913 |
| quantity_direct | normal_answer | 0.3450 | 0.0000 | 0.0880 | 2.8240 |
| quantity_direct | digit_spaced | 0.3810 | 0.0000 | 0.0990 | 3.4500 |

## By-Task Results

| preset | answer_format | task_type | count | NEM | empty_rate | avg_tokens |
| --- | --- | --- | --- | --- | --- | --- |
| arithmetic | normal_answer | arithmetic.add | 406 | 0.0000 | 0.0665 | 2.8670 |
| arithmetic | normal_answer | arithmetic.compare_sum | 405 | 0.0000 | 0.1877 | 2.6247 |
| arithmetic | normal_answer | arithmetic.double_step | 379 | 0.0053 | 0.0660 | 2.8681 |
| arithmetic | normal_answer | arithmetic.missing_addend | 415 | 0.0096 | 0.0000 | 3.0000 |
| arithmetic | normal_answer | arithmetic.subtract | 395 | 0.0253 | 0.0582 | 2.8835 |
| arithmetic | digit_spaced | arithmetic.add | 405 | 0.0000 | 0.0000 | 3.9358 |
| arithmetic | digit_spaced | arithmetic.compare_sum | 422 | 0.0000 | 0.1754 | 3.5427 |
| arithmetic | digit_spaced | arithmetic.double_step | 367 | 0.0054 | 0.0136 | 3.8747 |
| arithmetic | digit_spaced | arithmetic.missing_addend | 391 | 0.0051 | 0.0000 | 3.9693 |
| arithmetic | digit_spaced | arithmetic.subtract | 415 | 0.0217 | 0.0000 | 3.5133 |
| arithmetic | scratchpad | arithmetic.add | 406 | 0.0000 | 0.0000 | 33.6305 |
| arithmetic | scratchpad | arithmetic.compare_sum | 405 | 0.0000 | 0.0000 | 14.4815 |
| arithmetic | scratchpad | arithmetic.double_step | 379 | 0.0000 | 0.0000 | 29.8417 |
| arithmetic | scratchpad | arithmetic.missing_addend | 415 | 0.0000 | 0.0000 | 35.3012 |
| arithmetic | scratchpad | arithmetic.subtract | 395 | 0.0835 | 0.0000 | 38.2506 |
| arithmetic | reversed_answer | arithmetic.add | 406 | 0.0025 | 0.0148 | 4.3547 |
| arithmetic | reversed_answer | arithmetic.compare_sum | 405 | 0.0000 | 0.1877 | 3.2000 |
| arithmetic | reversed_answer | arithmetic.double_step | 379 | 0.0079 | 0.0660 | 3.3219 |
| arithmetic | reversed_answer | arithmetic.missing_addend | 415 | 0.0072 | 0.0000 | 3.7229 |
| arithmetic | reversed_answer | arithmetic.subtract | 395 | 0.0278 | 0.0025 | 3.9671 |
| sorting_short | normal_answer | sorting.ascending | 501 | 0.0080 | 0.0659 | 7.6667 |
| sorting_short | normal_answer | sorting.descending | 499 | 0.0200 | 0.0601 | 7.6693 |
| sorting_short | digit_spaced | sorting.ascending | 493 | 0.0122 | 0.1826 | 9.6653 |
| sorting_short | digit_spaced | sorting.descending | 507 | 0.0158 | 0.3037 | 8.5858 |
| sorting_short | scratchpad | sorting.ascending | 501 | 0.0060 | 0.0000 | 118.6387 |
| sorting_short | scratchpad | sorting.descending | 499 | 0.0100 | 0.0000 | 116.5331 |
| state_change | normal_answer | state_change.add | 299 | 0.0033 | 0.0000 | 3.0000 |
| state_change | normal_answer | state_change.subtract | 303 | 0.0297 | 0.0000 | 3.0000 |
| state_change | scratchpad | state_change.add | 299 | 0.0234 | 0.0000 | 38.0535 |
| state_change | scratchpad | state_change.subtract | 303 | 0.0627 | 0.0000 | 54.3069 |
| quantity_direct | normal_answer | quantity.direct | 344 | 0.1424 | 0.0000 | 3.0000 |
| quantity_direct | normal_answer | quantity.known_zero | 342 | 0.7427 | 0.2573 | 2.4854 |
| quantity_direct | normal_answer | quantity.location_direct | 314 | 0.1338 | 0.0000 | 3.0000 |
| quantity_direct | digit_spaced | quantity.direct | 331 | 0.2145 | 0.0121 | 3.9637 |
| quantity_direct | digit_spaced | quantity.known_zero | 341 | 0.7419 | 0.2581 | 2.4839 |
| quantity_direct | digit_spaced | quantity.location_direct | 328 | 0.1738 | 0.0213 | 3.9360 |

## Format Comparisons

| comparison | left | right | left NEM | right NEM | delta NEM |
| --- | --- | --- | --- | --- | --- |
| arithmetic_normal_vs_digit_spaced | normal | digit_spaced | 0.0080 | 0.0065 | -0.0015 |
| arithmetic_normal_vs_scratchpad | normal | scratchpad | 0.0080 | 0.0165 | 0.0085 |
| arithmetic_normal_vs_reversed | normal | reversed | 0.0080 | 0.0090 | 0.0010 |
| sorting_short_normal_vs_digit_spaced | normal | digit_spaced | 0.0140 | 0.0140 | 0.0000 |
| sorting_short_normal_vs_scratchpad | normal | scratchpad | 0.0140 | 0.0080 | -0.0060 |
| state_change_normal_vs_scratchpad | normal | scratchpad | 0.2433 | 0.2233 | -0.0200 |
| quantity_direct_normal_vs_digit_spaced | normal | digit_spaced | 0.3450 | 0.3810 | 0.0360 |

## Train-Subset Evals

| preset | answer_format | count | train-subset NEM | false_answer_rate |
| --- | --- | --- | --- | --- |
| arithmetic | normal_answer | 1000 | 0.0860 | 0.0000 |
| arithmetic | digit_spaced | 1000 | 0.0720 | 0.0000 |
| arithmetic | scratchpad | 1000 | 0.2690 | 0.0000 |
| arithmetic | reversed_answer | 1000 | 0.0940 | 0.0000 |
| sorting_short | normal_answer | 1000 | 0.8510 | 0.0000 |
| sorting_short | digit_spaced | 1000 | 0.7940 | 0.0000 |
| sorting_short | scratchpad | 1000 | 0.3910 | 0.0000 |
| state_change | normal_answer | 1000 | 0.6750 | 0.0000 |
| state_change | scratchpad | 1000 | 0.6660 | 0.0000 |
| quantity_direct | normal_answer | 1000 | 1.0000 | 0.0000 |
| quantity_direct | digit_spaced | 1000 | 1.0000 | 0.0000 |

Train-subset evals show the model can memorize/copy many train examples, especially sorting/state_change/quantity, while eval transfer stays much lower. Arithmetic scratchpad improves train-subset exact match from 0.086 to 0.269, but eval exact match remains only 0.0165.

## Key Failure Samples

| task_type | prompt | expected | predicted |
| --- | --- | --- | --- |
| arithmetic.add | case 78724. Найди сумму чисел 71 и 63. | ones: 1 + 3 = 4<br>tens: 7 + 6 = 13<br>carry: 1<br>answer: 134 | ones: 4 + 5 = 9<br>tens: 0 + 0 = 2<br>answer: 29 |
| sorting.ascending | case 48854. Запиши числа от меньшего к большему: 26, 34, 27, 78. | numbers: 26, 34, 27, 78<br>step 1: smallest is 26<br>remaining: 34, 27, 78<br>step 2: smallest i... | numbers: 26, 34, 27, 27<br>step 1: smallest is 27<br>remaining: 26, 27, 27<br>step 2: smallest i... |
| state_change.add | У Васи было 80 яблок. Васе дали ещё 22 яблока. Сколько яблок стало у Васи? | start: 80<br>change: +22<br>ones: 0 + 2 = 2<br>tens: 8 + 2 = 10<br>carry: 1<br>answer: 102 | given: 4<br>answer: 4 |
| quantity.direct | У Кати было 7 3 тетради. Сколько тетрадей было у Кати? | 7 3 | 2 3 |

## Conclusion

- `scratchpad` does not help strongly under exact full-answer scoring. It improves arithmetic over normal from 0.0080 to 0.0165, but this is below the useful arithmetic threshold of 0.03. It regresses sorting exact match from 0.0140 to 0.0080 and state_change from 0.2433 to 0.2233.
- `digit_spaced` helps loss and reduces some empty outputs, but exact-match gains are weak. Arithmetic falls from 0.0080 to 0.0065; sorting stays flat at 0.0140 and has high empty rate 0.2440; quantity improves from 0.3450 to 0.3810 but misses the useful threshold of 0.40.
- `reversed_answer` is not useful here: arithmetic moves only from 0.0080 to 0.0090.
- The model learns train examples much better than shifted eval examples. This pilot supports the previous diagnosis: the tiny Transformer mostly memorizes local formats and does not transfer numeric procedures reliably.
- Scratchpad evaluation is brittle because exact match requires the whole reasoning trace, not just the final answer. The low exact match may mix transfer failure with trace-format mismatch.

## Recommendation

1. Build a final-answer extractor for scratchpad eval so `answer: ...` can be scored separately from full trace exact match.
2. Run a same-range vs shifted-range ablation next; current results still point at range transfer as the dominant failure.
3. Explore digit-level tokenizer or explicit number representation. `digit_spaced` improved quantity and eval loss but was not enough by itself.
4. Do not launch longer 30k/50k runs from these results alone; the pilot did not meet useful thresholds except for a near miss on quantity digit-spaced.

# M-11.0 Canonical Numeric Algorithm Format Report

## Checks

- `uv run ruff format src tests`: passed before pilot generation and will be rerun before commit
- `uv run ruff check src tests`: passed before pilot generation and will be rerun before commit
- `uv run pytest -q`: 125 passed before pilot generation and will be rerun before commit
- Source HEAD before final M-11.0 commit: `082237dcb61c80d4aacbebc4976bc877fbb05708`
- CUDA device: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`)

## Implemented

- `src/ai_brain/eval/final_answer.py`: marker-based final-answer extraction and normalized final-answer comparison.
- `eval-lm` predictions now include `final_expected`, `final_predicted`, `final_exact_match`, and `final_normalized_exact_match`.
- `summary.json`, diagnostics, and comparisons include final-answer metrics while preserving old exact-match metrics.
- `canonical_numeric` answer format is available through `--answer-format` for `generate-data` and `generate-data-split`.
- Supported canonical task families: arithmetic add/subtract/missing_addend/double_step/compare_sum, state_change add/subtract/no-change/unknown-start, sorting ascending/descending, quantity direct/location_direct/known_zero.

## Dataset Verification

| dataset | answer_format | train | eval | train dup | eval dup | task_types | sorting len |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m110_arithmetic_canonical | canonical_numeric | 20000 | 2000 | 0 | 0 | arithmetic.add, arithmetic.subtract, arithmetic.missing_addend, arithmetic.double_step, arithmetic.compare_sum |  |
| m110_state_change_canonical | canonical_numeric | 15000 | 1500 | 0 | 0 | state_change.add, state_change.subtract, state_change.other_subject_no_change, state_change.other_object_no_change, state_change.insufficient_start |  |
| m110_sorting_short_canonical | canonical_numeric | 10000 | 1000 | 0 | 0 | sorting.ascending, sorting.descending | train 3-4, eval 3-4 |
| m110_quantity_direct_canonical | canonical_numeric | 10000 | 1000 | 0 | 0 | quantity.direct, quantity.location_direct, quantity.known_zero |  |

All canonical manifests had `answer_format=canonical_numeric`, no train/eval prompt intersection, all preset task types present, and zero duplicate prompts. Transformed examples include `metadata.answer_format`, `metadata.original_prompt`, and `metadata.original_answer`.

### Sample Examples

| preset | task_type | prompt | answer sample |
| --- | --- | --- | --- |
| arithmetic | arithmetic.subtract | case 2311. Посчитай: 16 минус 4. | OP SUB<br>A 1 6<br>B 4<br>P0 6 4 B0 -> S2 B0<br>P1 1 0 B0 -> S1 B0<br>OUT 1 2 |
| arithmetic | arithmetic.add | case 7009. К 19 прибавь 22. Что получится? | OP ADD<br>A 1 9<br>B 2 2<br>P0 9 2 C0 -> S1 C1<br>P1 1 2 C1 -> S4 C0<br>OUT 4 1 |
| state_change | state_change.insufficient_start | Диме дали ещё 13 карандашей. Сколько карандашей стало у Димы? | OP STATE_UNKNOWN_START<br>OUT Недостаточно информации: неизвестно, сколько было сначала. |
| state_change | state_change.other_subject_no_change | У Пети было 16 яблок. Ире дали ещё 5 яблок. Сколько яблок стало у Пети? | OP STATE_NO_CHANGE<br>SUBJ DIFF<br>OBJ SAME<br>GIVEN 1 6<br>OUT 1 6 |
| sorting_short | sorting.descending | case 8017. Запиши числа от большего к меньшему: 3, 25, 8, 16. | OP SORT_DESC<br>N 3 \| 2 5 \| 8 \| 1 6<br>S0 MAX 2 5<br>S1 MAX 1 6<br>S2 MAX 8<br>S3 MAX 3<br>OUT 25, 16, 8, 3 |
| sorting_short | sorting.ascending | case 9266. Запиши числа от меньшего к большему: 2, 28, 7, 16. | OP SORT_ASC<br>N 2 \| 2 8 \| 7 \| 1 6<br>S0 MIN 2<br>S1 MIN 7<br>S2 MIN 1 6<br>S3 MIN 2 8<br>OUT 2, 7, 16, 28 |
| quantity_direct | quantity.location_direct | В комнате было 2 камня. Сколько камней было в комнате? | OP COPY_LOC_QTY<br>LOC SAME<br>OBJ SAME<br>N 2<br>OUT 2 |
| quantity_direct | quantity.direct | У Васи было 18 карандашей. Сколько карандашей было у Васи? | OP COPY_QTY<br>SUBJ SAME<br>OBJ SAME<br>N 1 8<br>OUT 1 8 |

## Training Runs

| preset | format | steps | checkpoint | final train loss | final eval loss | batch/OOM |
| --- | --- | --- | --- | --- | --- | --- |
| arithmetic | canonical_numeric | 10000 | runs/m110_arithmetic_canonical_tiny_10k/checkpoints/step_010000.pt | 0.0463 | 2.9008 | 8 / none |
| state_change | canonical_numeric | 8000 | runs/m110_state_change_canonical_tiny_8k/checkpoints/step_008000.pt | 0.0398 | 1.1020 | 8 / none |
| sorting_short | canonical_numeric | 8000 | runs/m110_sorting_short_canonical_tiny_8k/checkpoints/step_008000.pt | 0.0186 | 5.9694 | 8 / none |
| quantity_direct | canonical_numeric | 5000 | runs/m110_quantity_direct_canonical_tiny_5k/checkpoints/step_005000.pt | 0.0000 | 2.4666 | 8 / none |

## Eval Results

| preset | format | full NEM | final-answer NEM | false_answer_rate | empty_rate | avg_tokens |
| --- | --- | --- | --- | --- | --- | --- |
| arithmetic | canonical_numeric | 0.0020 | 0.0055 | 0.0000 | 0.0000 | 85.6720 |
| state_change | canonical_numeric | 0.2160 | 0.2400 | 0.0000 | 0.0000 | 56.6593 |
| sorting_short | canonical_numeric | 0.0040 | 0.0040 | 0.0000 | 0.0000 | 68.7990 |
| quantity_direct | canonical_numeric | 0.2990 | 0.3780 | 0.0000 | 0.0000 | 35.5290 |

## By-Task Final-Answer Results

| preset | task_type | count | full NEM | final-answer NEM | empty_rate | avg_tokens |
| --- | --- | --- | --- | --- | --- | --- |
| arithmetic | arithmetic.add | 438 | 0.0023 | 0.0023 | 0.0000 | 56.0251 |
| arithmetic | arithmetic.compare_sum | 394 | 0.0000 | 0.0000 | 0.0000 | 116.9416 |
| arithmetic | arithmetic.double_step | 373 | 0.0000 | 0.0054 | 0.0000 | 113.1582 |
| arithmetic | arithmetic.missing_addend | 408 | 0.0000 | 0.0074 | 0.0000 | 92.1740 |
| arithmetic | arithmetic.subtract | 387 | 0.0078 | 0.0129 | 0.0000 | 54.0439 |
| state_change | state_change.add | 286 | 0.0000 | 0.0000 | 0.0000 | 52.9091 |
| state_change | state_change.subtract | 296 | 0.0169 | 0.0405 | 0.0000 | 85.4662 |
| sorting_short | sorting.ascending | 514 | 0.0039 | 0.0039 | 0.0000 | 68.3988 |
| sorting_short | sorting.descending | 486 | 0.0041 | 0.0041 | 0.0000 | 69.2222 |
| quantity_direct | quantity.direct | 330 | 0.1121 | 0.1121 | 0.0000 | 41.8667 |
| quantity_direct | quantity.known_zero | 327 | 0.6972 | 0.9388 | 0.0000 | 19.3945 |
| quantity_direct | quantity.location_direct | 343 | 0.0991 | 0.0991 | 0.0000 | 44.8134 |

## Comparisons vs M-10.2

| comparison | left | right | left full NEM | right full NEM | full delta | left final NEM | right final NEM | final delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arithmetic_scratchpad_vs_canonical | m102_scratchpad | m110_canonical | 0.0165 | 0.0020 | -0.0145 | 0.0165 | 0.0055 | -0.0110 |
| arithmetic_normal_vs_canonical | m102_normal | m110_canonical | 0.0080 | 0.0020 | -0.0060 | 0.0080 | 0.0055 | -0.0025 |
| state_change_normal_vs_canonical | m102_normal | m110_canonical | 0.2433 | 0.2160 | -0.0273 | 0.2433 | 0.2400 | -0.0033 |
| sorting_short_normal_vs_canonical | m102_normal | m110_canonical | 0.0140 | 0.0040 | -0.0100 | 0.0140 | 0.0040 | -0.0100 |
| quantity_digit_spaced_vs_canonical | m102_digit_spaced | m110_canonical | 0.3810 | 0.2990 | -0.0820 | 0.3810 | 0.3780 | -0.0030 |

## Train-Subset Evals

| preset | format | count | full NEM | final-answer NEM | false_answer_rate |
| --- | --- | --- | --- | --- | --- |
| arithmetic | canonical_numeric | 1000 | 0.0330 | 0.0430 | 0.0000 |
| state_change | canonical_numeric | 1000 | 0.4120 | 0.6220 | 0.0000 |
| sorting_short | canonical_numeric | 1000 | 0.6580 | 0.7370 | 0.0000 |
| quantity_direct | canonical_numeric | 1000 | 1.0000 | 1.0000 | 0.0000 |

Train-subset results show the canonical format is learnable on seen examples for state_change, sorting, and quantity. The gap to shifted eval remains large, especially sorting 0.737 train-subset final NEM vs 0.004 eval final NEM.

## Failure Samples

| task_type | prompt | expected full trace | predicted full trace | expected final | predicted final |
| --- | --- | --- | --- | --- | --- |
| arithmetic.add | case 61094. Сколько будет 47 + 76? | OP ADD<br>A 4 7<br>B 7 6<br>P0 7 6 C0 -> S3 C1<br>P1 4 7 C1 -> S2 C1<br>OUT 1 2 3 | OP ADD<br>A 4<br>BB 2 4<br>P0 4 4 C0 -> S4 C0<br>P1 4 2 C0 -> S4 C0<br>OUT 4 4 | 1 2 3 | 4 4 |
| state_change.add | У Антона было 34 игрушки. Антону дали ещё 18 игрушек. Сколько игрушек стало у Антона? | OP STATE_ADD<br>SUBJ SAME<br>OBJ SAME<br>START 3 4<br>CHANGE 1 8<br>P0 4 8 C0 -> S2 C1<br>P1 3 1 C1 -> S5 C0<br>OUT 5 2 | OP STATE_NO_CHANGE<br>SUBJ DIFF<br>OBJ SAME<br>GIVEN 1 0<br>OUT 1 0 | 5 2 | 1 0 |
| sorting.ascending | case 55900. Упорядочь числа по возрастанию: 26, 69, 98. | OP SORT_ASC<br>N 2 6 \| 6 9 \| 9 8<br>S0 MIN 2 6<br>S1 MIN 6 9<br>S2 MIN 9 8<br>OUT 26, 69, 98 | OP SORT_ASC<br>N 2 6 \| 2 6 \| 2 1<br>S0 MIN 1 6<br>S1 MIN 2 6<br>S2 MIN 2 6<br>OUT 15, 26, 26 | 26, 69, 98 | 15, 26, 26 |
| quantity.direct | У Игоря было 77 яблок. Сколько яблок было у Игоря? | OP COPY_QTY<br>SUBJ SAME<br>OBJ SAME<br>N 7 7<br>OUT 7 7 | OP COPY_QTY<br>SUBJ SAME<br>OBJ SAME<br>N 1 5<br>OUT 1 5 | 7 7 | 1 5 |

## Conclusion

- Canonical format does not help enough in this pilot.
- Arithmetic canonical final-answer NEM is `0.0055`, below M-10.2 scratchpad full NEM `0.0165` and far below the useful threshold `0.05`.
- State_change canonical final-answer NEM is `0.2400`, essentially tied with M-10.2 normal `0.2433` and below useful threshold `0.32`.
- Sorting canonical final-answer NEM is `0.0040`, below M-10.2 normal `0.0140` and useful threshold `0.03`.
- Quantity canonical final-answer NEM is `0.3780`, about tied with M-10.2 digit_spaced `0.3810` and below useful threshold `0.45`.
- Canonical improves trace regularity and train-subset learning, but does not improve shifted-range transfer. The issue still looks like representation/range transfer rather than trace wording alone.

## Recommendation

1. Run same-range vs shifted-range ablation using canonical format to isolate range transfer from format learning.
2. Implement digit/place/role embeddings or a digit-level tokenizer before revisiting architecture.
3. Keep final-answer metrics as the primary metric for scratchpad/canonical experiments.
4. Revisit recurrent or other architectures only after representation work, because canonical formatting alone did not cross useful thresholds.

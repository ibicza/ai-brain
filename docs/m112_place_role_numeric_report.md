# M-11.2 Digit / Place / Role Representation Report

## Checks

- `uv run ruff format src tests`: passed, 51 files left unchanged
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: 136 passed
- Source HEAD before M-11.2 commit: `5511b4e7bc77df4936f2256a440d944bdb5b87e2`
- Device: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`)

## Implementation

- Added `place_role_numeric` to `--answer-format` for `generate-data`, `generate-data-split`, and `generate-range-ablation`.
- Added `src/ai_brain/data/number_format.py` helpers: `digits_of_number`, `place_names_for_digits`, `format_role_number`, and `format_plain_digit_number`.
- Prompt numbers are role/place tagged for quantity, arithmetic, state_change, and sorting_short task types.
- Answers use compact deterministic tags such as `A_T 7 A_U 1`, `P_U ...`, and `OUT_T 7 OUT_U 3`; sorting keeps final `OUT` as a comma-separated list.
- Final-answer normalization now treats role-tagged single-number `OUT_*` lines as numeric answers while preserving list answers.
- `generate-range-ablation` now accepts `--eval-count` as a shortcut for both eval splits.

## Dataset Verification

| preset | counts | ranges | intersections | duplicates | sorting lengths |
| --- | --- | --- | --- | --- | --- |
| arithmetic | eval_same=2000, eval_shifted=2000, train_same=20000 | eval_same=[0, 59], eval_shifted=[0, 160], train_same=[0, 60] | train/same=0, train/shifted=0, same/shifted=0 | eval_same=0, eval_shifted=0, train_same=0 |  |
| quantity_direct | eval_same=1000, eval_shifted=1000, train_same=10000 | eval_same=[1, 30], eval_shifted=[21, 100], train_same=[1, 30] | train/same=0, train/shifted=0, same/shifted=0 | eval_same=0, eval_shifted=0, train_same=0 |  |
| sorting_short | eval_same=1000, eval_shifted=1000, train_same=10000 | eval_same=[0, 49], eval_shifted=[20, 119], train_same=[0, 49] | train/same=0, train/shifted=0, same/shifted=0 | eval_same=0, eval_shifted=0, train_same=0 | eval_same=[3, 4], eval_shifted=[3, 4], train_same=[3, 4] |
| state_change | eval_same=1500, eval_shifted=1500, train_same=15000 | eval_same=[0, 30], eval_shifted=[1, 100], train_same=[0, 30] | train/same=0, train/shifted=0, same/shifted=0 | eval_same=0, eval_shifted=0, train_same=0 |  |

Sample examples are stored in `runs/m112_dataset_verification.json`; inspected samples show role-tagged prompt numbers for arithmetic, quantity, state_change, and sorting_short.

## Training Runs

| preset | steps | checkpoint | train loss | eval_same loss | batch | seq | note |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| quantity_direct | 5000 | `runs/m112_quantity_direct_place_role_tiny_5k/checkpoints/step_005000.pt` | 0.0000 | 0.0000 | 8 | 256 | no truncation observed in train output |
| arithmetic | 10000 | `runs/m112_arithmetic_place_role_tiny_10k/checkpoints/step_010000.pt` | 0.0487 | 0.0564 | 8 | 256 | arithmetic had ~36% truncation at seq256; zero supervised tokens stayed 0 |
| state_change | 8000 | `runs/m112_state_change_place_role_tiny_8k/checkpoints/step_008000.pt` | 0.0140 | 0.0150 | 8 | 256 | no truncation observed in train output |
| sorting_short | 8000 | `runs/m112_sorting_short_place_role_tiny_8k/checkpoints/step_008000.pt` | 0.0893 | 0.0922 | 8 | 256 | no truncation observed in train output |

## Same Vs Shifted Results

| preset | same full NEM | same final NEM | shifted full NEM | shifted final NEM | gap | shifted avg tokens | shifted empty |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| quantity_direct | 1.0000 | 1.0000 | 0.3830 | 0.3970 | 0.6030 | 45.9170 | 0.0000 |
| arithmetic | 0.0335 | 0.0375 | 0.0045 | 0.0065 | 0.0310 | 116.1805 | 0.0000 |
| state_change | 0.4193 | 0.6093 | 0.2367 | 0.3027 | 0.3067 | 88.0893 | 0.0000 |
| sorting_short | 0.0160 | 0.0520 | 0.0000 | 0.0000 | 0.0520 | 108.3820 | 0.0000 |

## Compare Vs M-11.1 Shifted Best

| preset | old shifted best | place_role shifted | delta | threshold | verdict |
| --- | ---: | ---: | ---: | --- | --- |
| quantity_direct | 0.3720 | 0.3970 | +0.0250 | useful 0.45, strong 0.60 | small improvement, below useful threshold |
| arithmetic | 0.0135 | 0.0065 | -0.0070 | useful 0.03, strong 0.08 | regression |
| state_change | 0.2327 | 0.3027 | +0.0700 | useful 0.32, strong 0.45 | small improvement, below useful threshold |
| sorting_short | 0.0090 | 0.0000 | -0.0090 | useful 0.03, strong 0.08 | regression |

## By-Task Results

| preset | split | task_type | count | full NEM | final NEM | false rate |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| quantity_direct | eval_same | quantity.direct | 314 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | eval_same | quantity.known_zero | 354 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | eval_same | quantity.location_direct | 332 | 1.0000 | 1.0000 | 0.0000 |
| quantity_direct | eval_shifted | quantity.direct | 332 | 0.1898 | 0.1898 | 0.0000 |
| quantity_direct | eval_shifted | quantity.known_zero | 334 | 0.7425 | 0.7844 | 0.0000 |
| quantity_direct | eval_shifted | quantity.location_direct | 334 | 0.2156 | 0.2156 | 0.0000 |
| arithmetic | eval_same | arithmetic.add | 398 | 0.0503 | 0.0578 | 0.0000 |
| arithmetic | eval_same | arithmetic.compare_sum | 414 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | eval_same | arithmetic.double_step | 398 | 0.0025 | 0.0151 | 0.0000 |
| arithmetic | eval_same | arithmetic.missing_addend | 396 | 0.0051 | 0.0051 | 0.0000 |
| arithmetic | eval_same | arithmetic.subtract | 394 | 0.1117 | 0.1117 | 0.0000 |
| arithmetic | eval_shifted | arithmetic.add | 394 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | eval_shifted | arithmetic.compare_sum | 411 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | eval_shifted | arithmetic.double_step | 401 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | eval_shifted | arithmetic.missing_addend | 397 | 0.0000 | 0.0000 | 0.0000 |
| arithmetic | eval_shifted | arithmetic.subtract | 397 | 0.0227 | 0.0327 | 0.0000 |
| state_change | eval_same | state_change.add | 298 | 0.0101 | 0.0101 | 0.0000 |
| state_change | eval_same | state_change.insufficient_start | 285 | 1.0000 | 1.0000 | 0.0000 |
| state_change | eval_same | state_change.other_object_no_change | 286 | 0.7483 | 1.0000 | 0.0000 |
| state_change | eval_same | state_change.other_subject_no_change | 305 | 0.3016 | 1.0000 | 0.0000 |
| state_change | eval_same | state_change.subtract | 326 | 0.1074 | 0.1074 | 0.0000 |
| state_change | eval_shifted | state_change.add | 308 | 0.0000 | 0.0000 | 0.0000 |
| state_change | eval_shifted | state_change.insufficient_start | 281 | 1.0000 | 1.0000 | 0.0000 |
| state_change | eval_shifted | state_change.other_object_no_change | 275 | 0.2691 | 0.2764 | 0.0000 |
| state_change | eval_shifted | state_change.other_subject_no_change | 334 | 0.0000 | 0.2904 | 0.0000 |
| state_change | eval_shifted | state_change.subtract | 302 | 0.0000 | 0.0000 | 0.0000 |
| sorting_short | eval_same | sorting.ascending | 507 | 0.0237 | 0.0592 | 0.0000 |
| sorting_short | eval_same | sorting.descending | 493 | 0.0081 | 0.0446 | 0.0000 |
| sorting_short | eval_shifted | sorting.ascending | 524 | 0.0000 | 0.0000 | 0.0000 |
| sorting_short | eval_shifted | sorting.descending | 476 | 0.0000 | 0.0000 | 0.0000 |

## Failure Samples

| preset | id | expected full | predicted full | expected final | predicted final |
| --- | --- | --- | --- | --- | --- |
| quantity_direct | quantity.direct:00000001 | OP COPY_QTY<br>SUBJ SAME<br>OBJ SAME<br>N_T 7 N_U 3<br>OUT_T 7 OUT_U 3 | OP COPY_QTY<br>SUBJ SAME<br>OBJ SAME<br>N_T 1 N_U 3<br>OUT_T 1 OUT_U 3 | OUT_T 7 OUT_U 3 | OUT_T 1 OUT_U 3 |
| arithmetic | arithmetic.compare_sum:00000002 | OP COMP_SUM<br>LEFT ADD<br>LA_T 2 LA_U 1<br>LB_T 3 LB_U 8<br>P_U LA_U 1 LB_U 8 C_IN 0 -> S_U 9 C_OUT 0<br>P_T LA_T 2 LB_T 3 C_IN 0 -> S_T 5 C_OUT 0<br>LEFT_OUT_T 5 LEFT_OUT_U 9<br>RIGHT ADD<br>RA_T 4 RA_U 4<br>RB_T 4 RB_U 5<br>P_U RA_U 4 RB_U 5 C_IN 0 -> S_... | OP COMP_SUM<br>LEFT ADD<br>LA_T 2 LA_U 1<br>LB_T 2 LB_U 8<br>P_U LA_U 1 LB_U 8 C_IN 0 -> S_U 7 C_OUT 0<br>P_T LA_T 1 LB_T 1 C_IN 0 -> S_T 3 C_OUT 0<br>LEFT_OUT_T_ | OUT_T 8 OUT_U 9 | OP COMP_SUM<br>LEFT ADD<br>LA_T 2 LA_U 1<br>LB_T 2 LB_U 8<br>P_U LA_U 1 LB_U 8 C_IN 0 -> S_U 7 C_OUT 0<br>P_T LA_T 1 LB_T 1 C_IN 0 -> S_T 3 C_OUT 0<br>LEFT_OUT_T_ |
| state_change | state_change.other_subject_no_change:00000001 | OP STATE_NO_CHANGE<br>SUBJ DIFF<br>OBJ SAME<br>GIVEN_T 9 GIVEN_U 2<br>OUT_T 9 OUT_U 2 | OP STATE_NO_CHANGE<br>SUBJ SAME<br>OBJ DIFF<br>GIVEN_T 1 GIVEN_U 2<br>OUT_T 3 OUT_U 2 | OUT_T 9 OUT_U 2 | OUT_T 3 OUT_U 2 |
| sorting_short | sorting.ascending:00000000 | OP SORT_ASC<br>N0_H 1 N0_T 1 N0_U 0 \| N1_T 2 N1_U 0 \| N2_T 4 N2_U 8 \| N3_T 5 N3_U 5<br>S0 MIN N1_T 2 N1_U 0<br>S1 MIN N2_T 4 N2_U 8<br>S2 MIN N3_T 5 N3_U 5<br>S3 MIN N0_H 1 N0_T 1 N0_U 0<br>OUT 20, 48, 55, 110 | OP SORT 1 N1_T 1 N2_U 0 \| N2_T 1 N2_1212121212121212121212121212121212121212121212121212121212 N2_U 0<br>S0_T 1<br>S1_U 0<br>S0 MAX N1 MIN0_U 0<br>OUT 10, 10, 10, 10 | 20, 48, 55, 110 | 10, 10, 10, 10 |

## Conclusion

`place_role_numeric` does not help enough as a pure text-level intervention.

- `quantity_direct`: same-range remains solved and shifted improves only slightly, from 0.3720 to 0.3970, below the useful 0.45 threshold.
- `state_change`: shifted improves from 0.2327 to 0.3027, also below the useful 0.32 threshold, but close enough to show role/place tags carry some signal.
- `arithmetic`: both same and shifted regress; the format is long and ~36% of arithmetic examples truncate at `sequence_length=256`, so it is not a good text-only fix in this setup.
- `sorting_short`: severe regression even on same-range, suggesting verbose role-tag traces made generation harder than the previous normal/canonical formats.

Overall verdict: place/role text tags help same-range only weakly and do not solve shifted transfer. The useful signal is that explicit numeric structure may help state/quantity, but the text representation is too verbose and brittle.

## Recommendation

Next best step: implement trainable digit/place/role embeddings or a compact digit-level tokenizer experiment, not more verbose text tags. If using text tags again, shorten the format first and avoid arithmetic truncation before judging architecture changes.

# M-14 Digit Table Curriculum Report

## Checks

- `uv run ruff format src tests`: passed
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: passed, 153 tests
- pre-M14 base commit: `54a742a`
- device: NVIDIA GeForce RTX 3050 Laptop GPU (cuda:0)

## M-13 Recap

M-13 showed that arithmetic fails before broad composition: digit add/sub and unseen digit combinations were weak, while same-range two-digit tasks could be memorized. M-14 therefore tests whether explicit full digit-table coverage is enough to make the tiny Transformer transfer digit operations into held-out two-digit composition.

## Dataset Coverage

Generated with `uv run ai-brain generate-digit-table-curriculum --output-dir datasets\m14_digit_table_curriculum --seed 31000 --digit-table-repeats 10 --eval-digit-table-repeats 2 --composition-count 8000 --eval-composition-count 2000 --answer-format compact_digit_trace`.

- train digit-table examples: 4000
- eval digit-table seen/holdout examples: 800 / 800
- train 2digit composition examples: 8000
- eval 2digit same/holdout/far examples: 2000 / 2000 / 2000
- digit pair coverage: add pairs 100, sub pairs 100
- carry coverage: carry_in=[0, 1], carry_out=[0, 1]
- borrow coverage: borrow_in=[0, 1], borrow_out=[0, 1]
- all eval prompt intersections zero: `True`
- composition holdout unseen vs composition train: 0.2948
- composition holdout combos seen in digit table: 1.0000

## Training Recipes

Official recipes:

- Recipe A `mixed_from_start`: 8k steps on `train_mixed`, seq256.
- Recipe B `staged`: 5k digit table seq128, then 5k composition seq256 from checkpoint, then 3k mixed replay seq256.

Additional targeted diagnostics, because official A/B did not reach useful digit-table thresholds:

- Recipe C: digit-table-only 20k plus best-loss checkpoint after 2k continuation, seq128.
- Recipe D: composition continuation and mixed replay from the best Recipe C digit-table checkpoint.

| recipe | step | train loss | eval loss | grad norm | init |
|---|---:|---:|---:|---:|---|
| A mixed_from_start 8k | 8000 | 0.0923 | 1.8372 | 0.5019 | none |
| B1 staged digit 5k | 5000 | 0.2643 | 0.3307 | 1.2290 | none |
| B2 staged composition 5k | 5000 | 0.0174 | 2.2192 | 0.4918 | from step 5000, loaded 28, skipped 1 |
| B3 staged mixed replay 3k | 3000 | 0.0010 | 2.1223 | 0.0920 | from step 5000, loaded 29, skipped 0 |
| C digit-table 20k diagnostic | 20000 | 0.0146 | 0.1129 | 0.9343 | none |
| C continuation 5k diagnostic | 5000 | 0.0316 | 0.1693 | 4.4750 | from step 20000, loaded 29, skipped 0 |
| D strong-digit composition 5k | 5000 | 0.0058 | 2.9045 | 0.1918 | from step 2000, loaded 28, skipped 1 |
| D strong-digit mixed replay 3k | 3000 | 0.0027 | 2.8575 | 0.2817 | from step 5000, loaded 29, skipped 0 |

## Eval Results

| recipe | split | final NEM | full NEM | empty | false answer | avg tokens |
|---|---:|---:|---:|---:|---:|---:|
| A mixed_from_start 8k | eval_digit_table_holdout | 0.1000 | 0.1000 | 0.0000 | 0.0000 | 7.00 |
| A mixed_from_start 8k | eval_2digit_same | 0.8935 | 0.8765 | 0.0000 | 0.0000 | 39.00 |
| A mixed_from_start 8k | eval_2digit_holdout_combo | 0.0075 | 0.0005 | 0.0000 | 0.0000 | 39.01 |
| A mixed_from_start 8k | eval_2digit_far | 0.0125 | 0.0000 | 0.0000 | 0.0000 | 39.01 |
| B3 staged mixed replay 3k | eval_digit_table_holdout | 0.2100 | 0.2100 | 0.0000 | 0.0000 | 7.01 |
| B3 staged mixed replay 3k | eval_2digit_same | 0.9400 | 0.9390 | 0.0000 | 0.0000 | 39.01 |
| B3 staged mixed replay 3k | eval_2digit_holdout_combo | 0.0155 | 0.0120 | 0.0000 | 0.0000 | 38.95 |
| B3 staged mixed replay 3k | eval_2digit_far | 0.0175 | 0.0000 | 0.0000 | 0.0000 | 38.82 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | 0.8100 | 0.8100 | 0.0200 | 0.0000 | 6.88 |
| D strong-digit composition 5k | eval_digit_table_holdout | 0.0000 | 0.0000 | 0.0025 | 0.0000 | 15.37 |
| D strong-digit composition 5k | eval_2digit_same | 0.8655 | 0.8655 | 0.0000 | 0.0000 | 39.01 |
| D strong-digit composition 5k | eval_2digit_holdout_combo | 0.0650 | 0.0595 | 0.0000 | 0.0000 | 39.01 |
| D strong-digit composition 5k | eval_2digit_far | 0.0185 | 0.0000 | 0.0000 | 0.0000 | 39.00 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | 0.8250 | 0.8250 | 0.0000 | 0.0000 | 7.00 |
| D strong-digit mixed replay 3k | eval_2digit_same | 0.8950 | 0.8915 | 0.0000 | 0.0000 | 38.97 |
| D strong-digit mixed replay 3k | eval_2digit_holdout_combo | 0.0645 | 0.0625 | 0.0000 | 0.0000 | 38.95 |
| D strong-digit mixed replay 3k | eval_2digit_far | 0.0175 | 0.0000 | 0.0000 | 0.0000 | 38.98 |

## By Group

| recipe | split | group | count | final NEM |
|---|---|---|---:|---:|
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_add | 400 | 0.8050 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_sub | 400 | 0.8150 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_add_no_carry | 110 | 0.8273 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_add_carry/carry_in | 290 | 0.7966 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_sub_no_borrow | 110 | 0.8273 |
| C best-loss digit-table 22k diagnostic | eval_digit_table_holdout | digit_sub_borrow/borrow_in | 290 | 0.8103 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_add | 400 | 0.7950 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_sub | 400 | 0.8550 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_add_no_carry | 110 | 0.7818 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_add_carry/carry_in | 290 | 0.8000 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_sub_no_borrow | 110 | 0.7818 |
| D strong-digit mixed replay 3k | eval_digit_table_holdout | digit_sub_borrow/borrow_in | 290 | 0.8828 |
| D strong-digit mixed replay 3k | eval_2digit_holdout_combo | 2digit_add | 1030 | 0.0350 |
| D strong-digit mixed replay 3k | eval_2digit_holdout_combo | 2digit_sub | 970 | 0.0959 |
| D strong-digit mixed replay 3k | eval_2digit_far | 2digit_add | 995 | 0.0000 |
| D strong-digit mixed replay 3k | eval_2digit_far | 2digit_sub | 1005 | 0.0348 |

## Failure Samples

- C best-loss digit-table 22k diagnostic / eval_digit_table_holdout / arithmetic.digit_add_with_carry_input
  prompt: `case 31003000010. ADD_DIGIT a=2 b=1 c=1`
  expected final: `S 4 C 0`; predicted final: `S 3 C 0`
- D strong-digit mixed replay 3k / eval_2digit_holdout_combo / arithmetic.sub_2digit_composed
  prompt: `case 31006. SUB2_COMPOSED 69 - 64`
  expected final: `5`; predicted final: `0`

## Recipe Comparison

- Official Recipe A learned 2digit same-range well (`final NEM 0.8935`) but failed digit-table eval (`0.1000`) and composition holdout (`0.0075`).
- Official Recipe B with short digit pretraining also learned 2digit same-range (`0.9400` after replay) but stayed poor on digit-table holdout (`0.2100`) and composition holdout (`0.0155`).
- Targeted Recipe C shows the digit table is learnable by this tiny model with enough focused steps: best-loss checkpoint reached digit-table holdout `0.8100`, with digit_add about `0.8050` and digit_sub about `0.8150`.
- Recipe D shows that learned digit operations do not transfer cleanly into two-digit composition: holdout-combo improved over official B but only to `0.0645`, far remained `0.0175`.

## Conclusion

M-14 answers the key question: full digit-table coverage can make the tiny Transformer learn basic digit operations, but only with substantially more focused digit-table training than the initial 5k staged recipe. The composition failure remains. Even when digit-table holdout reaches useful-level accuracy, two-digit holdout-combo stays far below useful thresholds: add `0.0350`, sub `0.0959` in the strongest replay run.

Interpretation: the blocker is no longer only basic digit operation learning. After explicit table training, the remaining failure is positional composition and carry/borrow reuse inside the compact trace. Composition training memorizes same-range prompts but does not reliably bind unseen digit rows into `U/T/OUT` positions.

Recommendation: next step should be a positional carry/borrow composition curriculum or digit/place/role embeddings. Do not move to a bigger broad model yet; first make the model preserve digit-table knowledge while composing two-place operations.

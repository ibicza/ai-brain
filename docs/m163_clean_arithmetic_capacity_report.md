# M-16.3 / M-16.4 Clean Arithmetic Capacity Report

## Checks

- `uv run ruff format src tests scripts`
- `uv run ruff check src tests scripts`
- `uv run pytest -q`
- commit: `5cf35a9`
- device: `cuda:0` / `NVIDIA GeForce RTX 3050 Laptop GPU`

## Clean Benchmark Verification

| split | count | prompt overlap | composition overlap | digit coverage | carry distribution | 2digit/3digit |
| --- | ---: | ---: | ---: | --- | --- | --- |
| eval_seen_combo_2digit | 500 | 500 | 500 | 197/299 | `{'no_carry': 247, 'units_carry': 253}` | `500/0` |
| eval_seen_combo_3digit | 500 | 500 | 500 | 200/299 | `{'final_carry': 500}` | `0/500` |
| eval_train_exact | 3000 | 3000 | 3000 | 299/299 | `{'final_carry': 1500, 'no_carry': 750, 'units_carry': 750}` | `1500/1500` |
| eval_unseen_combo_2digit | 500 | 0 | 0 | 198/299 | `{'no_carry': 321, 'units_carry': 179}` | `500/0` |
| eval_unseen_combo_3digit | 500 | 0 | 0 | 199/299 | `{'final_carry': 500}` | `0/500` |
| eval_wrapper_holdout | 500 | 0 | 500 | 278/299 | `{'final_carry': 233, 'no_carry': 121, 'units_carry': 146}` | `267/233` |
| train | 3000 | 3000 | 3000 | 299/299 | `{'final_carry': 1500, 'no_carry': 750, 'units_carry': 750}` | `1500/1500` |

## Tiny Fit Audit

| variant | params | steps | batch | train loss | eval loss | train NEM | seen2 | seen3 | unseen2 | unseen3 | units | tens | hundreds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| random_tiny_10k | 1461760 | 10000 | 8 | 0.0000 | 0.0144 | 0.9813 | 0.9660 | 0.9920 | 0.9480 | 0.9840 | 0.9920 | 0.9785 | 1.0000 |

## Digit-Table Transfer

| variant | params | steps | batch | train loss | eval loss | train NEM | seen2 | seen3 | unseen2 | unseen3 | units | tens | hundreds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| random_tiny_10k | 1461760 | 10000 | 8 | 0.0000 | 0.0144 | 0.9813 | 0.9660 | 0.9920 | 0.9480 | 0.9840 | 0.9920 | 0.9785 | 1.0000 |
| digit_pretrained_tiny_10k | 1461760 | 10000 | 8 | 0.0004 | 0.0029 | 0.9603 | 0.9920 | 0.9420 | 0.9760 | 0.9040 | 0.9935 | 0.9595 | 0.9990 |
| digit_pretrained_replay_tiny_10k | 1461760 | 10000 | 8 | 0.0146 | 0.0301 | 0.9073 | 0.8800 | 0.9240 | 0.8560 | 0.9140 | 0.9405 | 0.9515 | 0.9950 |

## Capacity Sweep

| variant | params | steps | batch | train loss | eval loss | train NEM | seen2 | seen3 | unseen2 | unseen3 | units | tens | hundreds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| random_tiny_10k | 1461760 | 10000 | 8 | 0.0000 | 0.0144 | 0.9813 | 0.9660 | 0.9920 | 0.9480 | 0.9840 | 0.9920 | 0.9785 | 1.0000 |
| arithmetic_3m_10k | 5289472 | 10000 | 8 | 0.0000 | 0.0105 | 0.9820 | 0.9760 | 0.9880 | 0.9840 | 0.9920 | 0.9990 | 0.9855 | 1.0000 |
| arithmetic_10m_10k | 12067968 | 10000 | 8 | 0.0000 | 0.0110 | 0.9523 | 0.9520 | 0.9500 | 0.9520 | 0.9320 | 0.9735 | 0.9720 | 0.9990 |

## Multi-Seed Results

`arithmetic_3m` triggered multi-seed validation because it improved unseen-combo NEM over S0.

| metric | mean | std | min | max |
| --- | ---: | ---: | ---: | ---: |
| train NEM | 0.9602 | 0.0154 | 0.9483 | 0.9820 |
| seen2 | 0.9500 | 0.0193 | 0.9300 | 0.9760 |
| seen3 | 0.9733 | 0.0104 | 0.9660 | 0.9880 |
| unseen2 | 0.9300 | 0.0386 | 0.8960 | 0.9840 |
| unseen3 | 0.9753 | 0.0125 | 0.9620 | 0.9920 |
| units | 0.9848 | 0.0128 | 0.9680 | 0.9990 |

## Failure Samples

### arithmetic_10m_10k

- `ADD 41 + 19` expected `60`, predicted `50`, carry `units_carry`, wrong `tens`
- `ADD 35 + 37` expected `72`, predicted `82`, carry `units_carry`, wrong `tens`
- `ADD 47 + 14` expected `61`, predicted `51`, carry `units_carry`, wrong `tens`
- `ADD 24 + 35` expected `59`, predicted `69`, carry `no_carry`, wrong `tens`
- `ADD 44 + 48` expected `92`, predicted `91`, carry `units_carry`, wrong `units`

### arithmetic_3m_10k

- `ADD 25 + 26` expected `51`, predicted `41`, carry `units_carry`, wrong `tens`
- `ADD 21 + 28` expected `49`, predicted `39`, carry `no_carry`, wrong `tens`
- `ADD 23 + 27` expected `50`, predicted `40`, carry `units_carry`, wrong `tens`
- `ADD 34 + 40` expected `74`, predicted `84`, carry `no_carry`, wrong `tens`
- `ADD 05 + 70` expected `75`, predicted `74`, carry `no_carry`, wrong `units`

### arithmetic_3m_seed316302_10k

- `ADD 50 + 40` expected `90`, predicted `100`, carry `no_carry`, wrong `tens`
- `ADD 23 + 09` expected `32`, predicted `22`, carry `units_carry`, wrong `tens`
- `ADD 14 + 20` expected `34`, predicted `24`, carry `no_carry`, wrong `tens`
- `ADD 26 + 08` expected `34`, predicted `24`, carry `units_carry`, wrong `tens`
- `ADD 13 + 22` expected `35`, predicted `25`, carry `no_carry`, wrong `tens`

### arithmetic_3m_seed316303_10k

- `ADD 14 + 20` expected `34`, predicted `44`, carry `no_carry`, wrong `tens`
- `ADD 82 + 03` expected `85`, predicted `84`, carry `no_carry`, wrong `units`
- `ADD 09 + 85` expected `94`, predicted `104`, carry `units_carry`, wrong `tens`
- `ADD 62 + 33` expected `95`, predicted `94`, carry `no_carry`, wrong `units`
- `ADD 84 + 09` expected `93`, predicted `103`, carry `units_carry`, wrong `tens`

### digit_pretrained_replay_tiny_10k

- `ADD 65 + 07` expected `72`, predicted `73`, carry `units_carry`, wrong `units`
- `ADD 08 + 21` expected `29`, predicted `39`, carry `no_carry`, wrong `tens`
- `ADD 23 + 09` expected `32`, predicted `33`, carry `units_carry`, wrong `units`
- `ADD 03 + 79` expected `82`, predicted `83`, carry `units_carry`, wrong `units`
- `ADD 49 + 28` expected `77`, predicted `67`, carry `units_carry`, wrong `tens`

### digit_pretrained_tiny_10k

- `ADD 19 + 20` expected `39`, predicted `49`, carry `no_carry`, wrong `tens`
- `ADD 37 + 20` expected `57`, predicted `56`, carry `no_carry`, wrong `units`
- `ADD 56 + 43` expected `99`, predicted `109`, carry `no_carry`, wrong `tens`
- `ADD 21 + 16` expected `37`, predicted `36`, carry `no_carry`, wrong `units`
- `ADD 38 + 60` expected `98`, predicted `108`, carry `no_carry`, wrong `tens`

### random_tiny_10k

- `ADD 14 + 11` expected `25`, predicted `15`, carry `no_carry`, wrong `tens`
- `ADD 02 + 25` expected `27`, predicted `17`, carry `no_carry`, wrong `tens`
- `ADD 08 + 21` expected `29`, predicted `19`, carry `no_carry`, wrong `tens`
- `ADD 13 + 12` expected `25`, predicted `15`, carry `no_carry`, wrong `tens`
- `ADD 03 + 26` expected `29`, predicted `19`, carry `no_carry`, wrong `tens`


## Decision

Outcome E: the clean benchmark removed the M-16.2 wrapper/noise failure and shows high transfer, but no tested model reached the strong train-fit criterion of 0.99 reliably. This is not a clean systematic-rule failure yet.

## Next Milestone

Inspect clean eval/data/objective details and generation failures before M-17. A short 20k clean-fit follow-up for the smallest strong model is more justified than RFFT right now.

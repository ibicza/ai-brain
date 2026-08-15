# M-16.2 Balanced Addition OOD Factorization Report

## Checks

- `uv run ruff format src tests scripts\m162_balanced_addition.py`
- `uv run ruff check src tests scripts\m162_balanced_addition.py`
- `uv run pytest -q`
- commit: `f5bedb1`
- device: `cuda:0` / `NVIDIA GeForce RTX 3050 Laptop GPU`

## Official Position References

- Position Coupling source: [HanseulJo/position-coupling](https://github.com/HanseulJo/position-coupling), `src/data/addition.py`, `AdditionDatasetWithCoupledPositions`.
- Abacus source: [mcleish7/arithmetic](https://github.com/mcleish7/arithmetic), `abacus.py`, `Abacus.helper`.
- M-16.2 uses normal input and LSD-first output for Position Coupling, and reversed digit spans for Abacus.

## Dataset Verification

- train examples: `6000`
- train base composition combos: `2000`
- train tag repeats per combo: `3`
- eval examples per A/B/C/D cell: `500`
- local digit-pair/carry coverage complete: `True` (299/299)
- train carry buckets: `{'final_carry': 3000, 'no_carry': 1500, 'units_carry': 1500}`
- train output lengths: `{'2_digit': 3000, '3_digit': 3000}`
- prompt intersections: `{'abacus': {'a_seen_combo_familiar_length': 0, 'b_seen_combo_novel_length': 0, 'c_unseen_combo_familiar_length': 0, 'd_unseen_combo_novel_length': 0}, 'position_coupling': {'a_seen_combo_familiar_length': 0, 'b_seen_combo_novel_length': 0, 'c_unseen_combo_familiar_length': 0, 'd_unseen_combo_novel_length': 0}, 'tiny_digit_safe': {'a_seen_combo_familiar_length': 0, 'b_seen_combo_novel_length': 0, 'c_unseen_combo_familiar_length': 0, 'd_unseen_combo_novel_length': 0}}`

## Main Results

| variant | eval cell | count | final NEM | per-digit | units | tens | hundreds | carry-length | empty | false | avg tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| abacus | a_seen_combo_familiar_length | 500 | 0.0000 | 0.1920 | 0.0000 | 0.3840 | n/a | 0.9900 | 0.0000 | 1.0000 | 15.0200 |
| abacus | b_seen_combo_novel_length | 500 | 0.0000 | 0.4740 | 0.0000 | 0.4620 | 0.9600 | 0.9600 | 0.0000 | 1.0000 | 16.9200 |
| abacus | c_unseen_combo_familiar_length | 500 | 0.0000 | 0.2180 | 0.0000 | 0.4360 | n/a | 0.9860 | 0.0000 | 1.0000 | 15.0280 |
| abacus | d_unseen_combo_novel_length | 500 | 0.0000 | 0.4573 | 0.0000 | 0.4260 | 0.9460 | 0.9460 | 0.0000 | 1.0000 | 16.8920 |
| position_coupling | a_seen_combo_familiar_length | 500 | 0.0000 | 0.0500 | 0.1000 | 0.0000 | n/a | 1.0000 | 0.0000 | 1.0000 | 15.0540 |
| position_coupling | b_seen_combo_novel_length | 500 | 0.0000 | 0.0353 | 0.1060 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 17.1260 |
| position_coupling | c_unseen_combo_familiar_length | 500 | 0.0000 | 0.0520 | 0.1040 | 0.0000 | n/a | 1.0000 | 0.0000 | 1.0000 | 15.0460 |
| position_coupling | d_unseen_combo_novel_length | 500 | 0.0000 | 0.0347 | 0.1040 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 17.1020 |
| tiny_digit_safe | a_seen_combo_familiar_length | 500 | 0.2340 | 0.5960 | 0.2820 | 0.9100 | n/a | 0.9900 | 0.0000 | 0.7660 | 10.0100 |
| tiny_digit_safe | b_seen_combo_novel_length | 500 | 0.2420 | 0.7367 | 0.2840 | 0.9260 | 1.0000 | 0.9940 | 0.0000 | 0.7580 | 11.0060 |
| tiny_digit_safe | c_unseen_combo_familiar_length | 500 | 0.2000 | 0.5750 | 0.2660 | 0.8840 | n/a | 0.9920 | 0.0000 | 0.8000 | 10.0080 |
| tiny_digit_safe | d_unseen_combo_novel_length | 500 | 0.2340 | 0.7287 | 0.2880 | 0.9040 | 0.9940 | 0.9860 | 0.0000 | 0.7660 | 11.0020 |

## Bucket Results

### abacus

| eval cell | bucket | count | final NEM | per-digit | carry-length |
| --- | --- | ---: | ---: | ---: | ---: |
| a_seen_combo_familiar_length | 2_digit | 500 | 0.0000 | 0.1920 | 0.9900 |
| a_seen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | no_carry | 255 | 0.0000 | 0.2275 | 0.9843 |
| a_seen_combo_familiar_length | units_carry | 245 | 0.0000 | 0.1551 | 0.9959 |
| b_seen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | 3_digit | 500 | 0.0000 | 0.4740 | 0.9600 |
| b_seen_combo_novel_length | final_carry | 500 | 0.0000 | 0.4740 | 0.9600 |
| b_seen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | 2_digit | 500 | 0.0000 | 0.2180 | 0.9860 |
| c_unseen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | no_carry | 298 | 0.0000 | 0.2601 | 0.9832 |
| c_unseen_combo_familiar_length | units_carry | 202 | 0.0000 | 0.1559 | 0.9901 |
| d_unseen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | 3_digit | 500 | 0.0000 | 0.4573 | 0.9460 |
| d_unseen_combo_novel_length | final_carry | 500 | 0.0000 | 0.4573 | 0.9460 |
| d_unseen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |

### position_coupling

| eval cell | bucket | count | final NEM | per-digit | carry-length |
| --- | --- | ---: | ---: | ---: | ---: |
| a_seen_combo_familiar_length | 2_digit | 500 | 0.0000 | 0.0500 | 1.0000 |
| a_seen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | no_carry | 255 | 0.0000 | 0.0686 | 1.0000 |
| a_seen_combo_familiar_length | units_carry | 245 | 0.0000 | 0.0306 | 1.0000 |
| b_seen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | 3_digit | 500 | 0.0000 | 0.0353 | 0.0000 |
| b_seen_combo_novel_length | final_carry | 500 | 0.0000 | 0.0353 | 0.0000 |
| b_seen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | 2_digit | 500 | 0.0000 | 0.0520 | 1.0000 |
| c_unseen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | no_carry | 298 | 0.0000 | 0.0688 | 1.0000 |
| c_unseen_combo_familiar_length | units_carry | 202 | 0.0000 | 0.0272 | 1.0000 |
| d_unseen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | 3_digit | 500 | 0.0000 | 0.0347 | 0.0000 |
| d_unseen_combo_novel_length | final_carry | 500 | 0.0000 | 0.0347 | 0.0000 |
| d_unseen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |

### tiny_digit_safe

| eval cell | bucket | count | final NEM | per-digit | carry-length |
| --- | --- | ---: | ---: | ---: | ---: |
| a_seen_combo_familiar_length | 2_digit | 500 | 0.2340 | 0.5960 | 0.9900 |
| a_seen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| a_seen_combo_familiar_length | no_carry | 255 | 0.1843 | 0.5588 | 0.9843 |
| a_seen_combo_familiar_length | units_carry | 245 | 0.2857 | 0.6347 | 0.9959 |
| b_seen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | 3_digit | 500 | 0.2420 | 0.7367 | 0.9940 |
| b_seen_combo_novel_length | final_carry | 500 | 0.2420 | 0.7367 | 0.9940 |
| b_seen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| b_seen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | 2_digit | 500 | 0.2000 | 0.5750 | 0.9920 |
| c_unseen_combo_familiar_length | 3_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | final_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| c_unseen_combo_familiar_length | no_carry | 298 | 0.1544 | 0.5419 | 0.9866 |
| c_unseen_combo_familiar_length | units_carry | 202 | 0.2673 | 0.6238 | 1.0000 |
| d_unseen_combo_novel_length | 2_digit | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | 3_digit | 500 | 0.2340 | 0.7287 | 0.9860 |
| d_unseen_combo_novel_length | final_carry | 500 | 0.2340 | 0.7287 | 0.9860 |
| d_unseen_combo_novel_length | no_carry | 0 | 0.0000 | 0.0000 | 0.0000 |
| d_unseen_combo_novel_length | units_carry | 0 | 0.0000 | 0.0000 | 0.0000 |

## Position ID Spot Check

### abacus

| text | token:our/reference positions |
| --- | --- |
| `ADD_ABACUS 74 + 12
= 86` | `7:1/1, 4:2/2, 1:1/1, 2:2/2, 8:1/1, 6:2/2` |
| `ADD_ABACUS 48 + 56
= 941` | `4:1/1, 8:2/2, 5:1/1, 6:2/2, 9:1/1, 4:2/2, 1:3/3` |
| `ADD_ABACUS 90 + 80
= 71` | `9:1/1, 0:2/2, 8:1/1, 0:2/2, 7:1/1, 1:2/2` |
| `ADD_ABACUS 85 + 25
= 011` | `8:1/1, 5:2/2, 2:1/1, 5:2/2, 0:1/1, 1:2/2, 1:3/3` |
| `ADD_ABACUS 99 + 99
= 891` | `9:1/1, 9:2/2, 9:1/1, 9:2/2, 8:1/1, 9:2/2, 1:3/3` |

### position_coupling

| text | token:our/reference positions |
| --- | --- |
| `ADD_PC 47 + 21
= 8 6` | `4:3/3, 7:2/2,  +:1/1, 2:3/3, 1:2/2, =:1/1, 8:2/2, 6:3/3` |
| `ADD_PC 84 + 65
= 9 4 1` | `8:3/3, 4:2/2,  +:1/1, 6:3/3, 5:2/2, =:1/1, 9:2/2, 4:3/3, 1:4/4` |
| `ADD_PC 09 + 08
= 7 1` | `0:3/3, 9:2/2,  +:1/1, 0:3/3, 8:2/2, =:1/1, 7:2/2, 1:3/3` |
| `ADD_PC 58 + 52
= 0 1 1` | `5:3/3, 8:2/2,  +:1/1, 5:3/3, 2:2/2, =:1/1, 0:2/2, 1:3/3, 1:4/4` |
| `ADD_PC 99 + 99
= 8 9 1` | `9:3/3, 9:2/2,  +:1/1, 9:3/3, 9:2/2, =:1/1, 8:2/2, 9:3/3, 1:4/4` |

## Interpretation

- `abacus`: seen 2-digit `0.0000`, seen 3-digit `0.0000`, unseen 2-digit `0.0000`, unseen 3-digit `0.0000`. Length gap `0.0000`, composition-combo gap `0.0000`.
- `position_coupling`: seen 2-digit `0.0000`, seen 3-digit `0.0000`, unseen 2-digit `0.0000`, unseen 3-digit `0.0000`. Length gap `0.0000`, composition-combo gap `0.0000`.
- `tiny_digit_safe`: seen 2-digit `0.2340`, seen 3-digit `0.2420`, unseen 2-digit `0.2000`, unseen 3-digit `0.2340`. Length gap `-0.0080`, composition-combo gap `0.0340`.
- Systematic unseen-composition generalization is still poor, so the next step should be explicit rule-following / RFFT-like curriculum rather than a new architecture.

## Failure Samples

### abacus / a_seen_combo_familiar_length

- `ADD_ABACUS 63 + 40 TAG DELTA` expected `40`, predicted `45`
- `ADD_ABACUS 71 + 57 TAG DELTA` expected `92`, predicted `85`
- `ADD_ABACUS 80 + 08 TAG DELTA` expected `88`, predicted `95`

### abacus / b_seen_combo_novel_length

- `ADD_ABACUS 25 + 84 TAG DELTA` expected `100`, predicted `105`
- `ADD_ABACUS 26 + 27 TAG BETA` expected `134`, predicted `147`
- `ADD_ABACUS 26 + 28 TAG DELTA` expected `144`, predicted `155`

### abacus / c_unseen_combo_familiar_length

- `ADD_ABACUS 80 + 50 TAG ALPHA` expected `13`, predicted `38`
- `ADD_ABACUS 85 + 04 TAG BETA` expected `98`, predicted `107`
- `ADD_ABACUS 95 + 80 TAG GAMMA` expected `67`, predicted `58`

### abacus / d_unseen_combo_novel_length

- `ADD_ABACUS 19 + 47 TAG ALPHA` expected `165`, predicted `178`
- `ADD_ABACUS 29 + 19 TAG GAMMA` expected `183`, predicted `178`
- `ADD_ABACUS 75 + 16 TAG BETA` expected `118`, predicted `115`

### position_coupling / a_seen_combo_familiar_length

- `ADD_PC 36 + 04 TAG DELTA` expected `40`, predicted `3`
- `ADD_PC 17 + 75 TAG DELTA` expected `92`, predicted `9`
- `ADD_PC 08 + 80 TAG DELTA` expected `88`, predicted `8`

### position_coupling / b_seen_combo_novel_length

- `ADD_PC 52 + 48 TAG DELTA` expected `100`, predicted `1`
- `ADD_PC 62 + 72 TAG BETA` expected `134`, predicted `1`
- `ADD_PC 62 + 82 TAG DELTA` expected `144`, predicted `1`

### position_coupling / c_unseen_combo_familiar_length

- `ADD_PC 08 + 05 TAG ALPHA` expected `13`, predicted `1`
- `ADD_PC 58 + 40 TAG BETA` expected `98`, predicted `8`
- `ADD_PC 59 + 08 TAG GAMMA` expected `67`, predicted `6`

### position_coupling / d_unseen_combo_novel_length

- `ADD_PC 91 + 74 TAG ALPHA` expected `165`, predicted `1`
- `ADD_PC 92 + 91 TAG GAMMA` expected `183`, predicted `1`
- `ADD_PC 57 + 61 TAG BETA` expected `118`, predicted `1`

### tiny_digit_safe / a_seen_combo_familiar_length

- `ADD 17 + 75 TAG DELTA` expected `92`, predicted `93`
- `ADD 60 + 06 TAG BETA` expected `66`, predicted `67`
- `ADD 60 + 39 TAG GAMMA` expected `99`, predicted `90`

### tiny_digit_safe / b_seen_combo_novel_length

- `ADD 52 + 48 TAG DELTA` expected `100`, predicted `101`
- `ADD 62 + 72 TAG BETA` expected `134`, predicted `133`
- `ADD 62 + 82 TAG DELTA` expected `144`, predicted `143`

### tiny_digit_safe / c_unseen_combo_familiar_length

- `ADD 08 + 05 TAG ALPHA` expected `13`, predicted `24`
- `ADD 59 + 08 TAG GAMMA` expected `67`, predicted `66`
- `ADD 00 + 90 TAG BETA` expected `90`, predicted `91`

### tiny_digit_safe / d_unseen_combo_novel_length

- `ADD 91 + 74 TAG ALPHA` expected `165`, predicted `166`
- `ADD 92 + 91 TAG GAMMA` expected `183`, predicted `182`
- `ADD 26 + 97 TAG GAMMA` expected `123`, predicted `124`

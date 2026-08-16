# M-17.5 Distractor Routing Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `550152b`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Oracle Mask Result

| family | length | normal | oracle |
|---|---:|---:|---:|
| natural_phrase | 1 | 0.5917 | 0.6667 |
| natural_phrase | 16 | 0.0000 | 0.8917 |
| natural_phrase | 2 | 0.4167 | 0.8250 |
| natural_phrase | 32 | 0.0000 | 0.0000 |
| natural_phrase | 4 | 0.0333 | 0.8417 |
| natural_phrase | 8 | 0.0000 | 0.9083 |
| neutral | 1 | 0.8917 | 0.7417 |
| neutral | 16 | 0.0000 | 0.7667 |
| neutral | 2 | 0.3333 | 0.7833 |
| neutral | 32 | 0.0000 | 0.0000 |
| neutral | 4 | 0.3000 | 0.8333 |
| neutral | 8 | 0.0583 | 0.9500 |
| previous_arithmetic | 1 | 0.1250 | 0.9333 |
| previous_arithmetic | 16 | 0.0000 | 0.0000 |
| previous_arithmetic | 2 | 0.0000 | 0.8000 |
| previous_arithmetic | 4 | 0.0000 | 0.8667 |
| previous_arithmetic | 8 | 0.0000 | 0.0000 |
| random_vocab | 1 | 0.4417 | 0.6667 |
| random_vocab | 16 | 0.0000 | 0.8500 |
| random_vocab | 2 | 0.0167 | 0.8250 |
| random_vocab | 32 | 0.0000 | 0.0000 |
| random_vocab | 4 | 0.0000 | 0.8167 |
| random_vocab | 8 | 0.0000 | 0.9583 |

## Attention Mass Analysis

| bucket | count | relevant mass | distractor mass | generated mass | rel/dist |
|---|---:|---:|---:|---:|---:|
| hard_negative.correct_False | 1436 | 0.4094 | 0.4982 | 0.0924 | 1.3815 |
| hard_negative.correct_True | 84 | 0.5735 | 0.2891 | 0.1374 | 2.8237 |
| natural_phrase.correct_False | 1560 | 0.5609 | 0.2790 | 0.1600 | 150.2325 |
| natural_phrase.correct_True | 1472 | 0.6292 | 0.1587 | 0.2121 | 198.2782 |
| neutral.correct_False | 788 | 0.6230 | 0.2475 | 0.1295 | 311.2938 |
| neutral.correct_True | 2500 | 0.6730 | 0.1198 | 0.2073 | 1519.5282 |
| previous_arithmetic.correct_False | 1032 | 0.4057 | 0.5155 | 0.0789 | 4.5061 |
| previous_arithmetic.correct_True | 256 | 0.5057 | 0.3280 | 0.1663 | 2.2465 |

## Distractor Curriculum Learning Curves

| run | clean | easy min16 | semantic min16 | hard/arith min8 |
|---|---:|---:|---:|---:|

## Relevance Classifier Metrics

not available

## Baseline vs Auxiliary vs Learned Gate vs Oracle

| run | clean | easy min16 | semantic min16 | hard/arith min8 |
|---|---:|---:|---:|---:|
| relative_shaw_baseline | 1.0000 | 0.0000 | 0.0000 | 0.0000 |
| oracle_mask_upper_bound | 1.0000 | 0.6667 | 0.6667 | 0.0000 |

## Differential Attention Comparison

missing

## Hard-Negative Robustness

| run | len1 | len2 | len4 | len8 | len16 |
|---|---:|---:|---:|---:|---:|

## Variable-Binding Routing Probe

missing

## Composition Retest

skipped: no complete routing candidate

## Recommended Attention/Routing Architecture

OUTCOME E: even oracle masking did not restore robustness; stop before learned routing.
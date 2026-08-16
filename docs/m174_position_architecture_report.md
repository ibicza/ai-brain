# M-17.4 Position Architecture Selection Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `e963b2a`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Implementation Notes

- Relative attention: Shaw et al.-style relation-aware self-attention using learned relative key/value embeddings indexed by clipped `j - i`; no learned absolute positional embedding is added in the primary relative run.
- Randomized PE: Ruoss et al.-style ordered subset sampling. For each training row, the script samples `sequence_length` positions without replacement from a virtual range, sorts them, and uses those absolute embedding rows while preserving token order.
- Sources: Shaw et al. 2018 https://arxiv.org/abs/1803.02155 ; Ruoss et al. 2023 https://arxiv.org/abs/2305.16843

## Dataset Verification

- train_per_op: `6000`
- eval_per_op: `100`
- prompt_intersections: `0`
- offsets: `[0, 1, 2, 4, 8, 16, 32, 64]`
- prefix_lengths: `[0, 1, 2, 4, 8, 16, 32]`
- distractor_types: `['neutral', 'random_vocab', 'natural_phrase', 'previous_arithmetic']`

## Fit Gate

| method | params | steps | train loss | train NEM | unseen ADD | unseen SUB | unseen NEM | gate |
|---|---|---:|---:|---:|---:|---:|---:|---|
| absolute | absolute:0 | 20000 | 0.0376 | 0.8700 | 0.7900 | 0.9300 | 0.8600 | fail |
| nope | nope:0 | 20000 | 0.0332 | 0.7850 | 0.6600 | 0.8100 | 0.7350 | fail |
| randomized_absolute_128 | randomized_absolute:128 | 20000 | 0.0785 | 0.4500 | 0.2700 | 0.5700 | 0.4200 | fail |
| relative_shaw | relative:0 | 20000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | pass |
| shifted_absolute_64 | shifted_absolute:64 | 20000 | 0.0042 | 0.9600 | 0.9800 | 0.9600 | 0.9700 | fail |

## Pure Offset Curves

### relative_shaw

| offset | ADD | SUB | overall |
|---:|---:|---:|---:|
| 0 | 1.0000 | 1.0000 | 1.0000 |
| 1 | 1.0000 | 1.0000 | 1.0000 |
| 2 | 1.0000 | 1.0000 | 1.0000 |
| 4 | 1.0000 | 1.0000 | 1.0000 |
| 8 | 1.0000 | 1.0000 | 1.0000 |
| 16 | 1.0000 | 1.0000 | 1.0000 |
| 32 | 1.0000 | 1.0000 | 1.0000 |
| 64 | 1.0000 | 1.0000 | 1.0000 |

## Distractor Prefix Curves

### relative_shaw

| distractor | len0 | len1 | len2 | len4 | len8 | len16 | len32 |
|---|---:|---:|---:|---:|---:|---:|---:|
| natural_phrase | 1.0000 | 0.6350 | 0.0150 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| neutral | 1.0000 | 0.8950 | 0.3300 | 0.3050 | 0.0550 | 0.0000 | 0.0000 |
| previous_arithmetic | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| random_vocab | 1.0000 | 0.4900 | 0.1850 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Position x History Matrix

### relative_shaw

| prefix_len \ offset | 0 | 8 | 32 |
|---:|---:|---:|---:|
| 0 | 1.0000 | 1.0000 | 1.0000 |
| 8 | 0.0550 | 0.0550 | 0.0550 |
| 32 | 0.0000 | 0.0000 | 0.0000 |

## Distractor Curriculum Comparison

| run | canonical | pure_min_32 | prefix_min_16 | prefix_min_32 |
|---|---:|---:|---:|---:|
| prefix_curriculum_relative_shaw | 0.9350 | 0.9350 | 0.1650 | 0.1650 |

## Semantic Context Retest

neutral/distractor prefix robustness did not reach >= .90

## Composition Retest

skipped: canonical=0.9350, pure_min=0.9350, prefix_min=0.1650, semantic_min=0.0000

## Recommended Default

Outcome A: `relative_shaw` solves or nearly solves global shift but distractors remain weak; next bottleneck is irrelevant-context filtering/routing.
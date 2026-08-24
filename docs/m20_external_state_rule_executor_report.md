# M-20 External-State Universal Rule Executor

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## M-19.2c Starting Point

M-19.2c showed that generated numeric state fails length OOD, while action-only TAKE/STOP with exact external state reaches 1.0 on 11..20 and 21..30.

## Action Metric Audit

- status: `passed`
- note: M-20 uses one parser for direct step metrics and closed-loop actions. The M-19.2c mismatch was a metric/reporting artifact, not an environment execution mismatch.

## Environment / State Model

The environment owns exact non-negative counts in registers `R0..R3`. The primary observation exposes only compact `E/NE` emptiness bits; exact counts are visible only in the explicit control split.

## Rule DSL

Model-facing clauses use compact aliases such as `0 R0 NE -> M R0 R2`; `M/D/H` map exactly to environment actions `MOVE_ONE/DROP_ONE/HALT`. Program keys stay in metadata, never in prompts.

## Clause Selection

| split | action accuracy | invalid action rate | counterfactual sensitivity |
|---|---:|---:|---:|
| seen_program_steps | 1.0000 | 0.0000 | n/a |
| state_21_50 | 1.0000 | 0.0000 | n/a |
| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| seen_program_steps | 1.0000 | 1.0000 | 0.0000 | 6.00 |
| state_21_50 | 1.0000 | 1.0000 | 0.0000 | 36.50 |
| heldout_program_instances | 0.3939 | 0.6970 | 0.3030 | 4.61 |

## Structured Action Generation

| split | action accuracy | invalid action rate | counterfactual sensitivity |
|---|---:|---:|---:|
| seen_program_steps | 1.0000 | 0.0000 | n/a |
| state_21_50 | 1.0000 | 0.0000 | n/a |
| heldout_program_instances | 0.4386 | 0.0000 | n/a |

## Counterfactual Rule Tests

| split | action accuracy | invalid action rate | counterfactual sensitivity |
|---|---:|---:|---:|
| counterfactual | 1.0000 | 0.0000 | 1.0000 |
| program_removed_control | 0.1667 | 0.0000 | 0.0000 |
| wrong_program_control | 1.0000 | 0.0000 | n/a |
| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| counterfactual | 1.0000 | 1.0000 | 0.0000 | 4.50 |

## Register Permutation

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| heldout_register_permutation | 0.5909 | 1.0000 | 0.0000 | 3.95 |

## Single-Rule Programs

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| seen_program_steps | 1.0000 | 1.0000 | 0.0000 | 6.00 |
| state_11_20 | 1.0000 | 1.0000 | 0.0000 | 16.50 |
| state_21_50 | 1.0000 | 1.0000 | 0.0000 | 36.50 |
| state_51_100 | 1.0000 | 1.0000 | 0.0000 | 76.50 |

## Multi-Clause Programs

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| heldout_program_instances | 0.0909 | 1.0000 | 0.0000 | 4.09 |

## Addition / MERGE_TWO

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| heldout_template_merge_two | 0.0909 | 1.0000 | 0.0000 | 8.50 |
| merge_two_11_20 | 0.0000 | 1.0000 | 0.0000 | 30.00 |
| merge_two_21_50 | 0.0000 | 1.0000 | 0.0000 | 60.00 |
| merge_two_51_100 | 0.0000 | 1.0000 | 0.0000 | 112.49 |

## Trajectory-Length Generalization

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| seen_program_steps | 1.0000 | 1.0000 | 0.0000 | 6.00 |
| state_11_20 | 1.0000 | 1.0000 | 0.0000 | 16.50 |
| state_21_50 | 1.0000 | 1.0000 | 0.0000 | 36.50 |
| state_51_100 | 1.0000 | 1.0000 | 0.0000 | 76.50 |

## Program Generator

- action train examples: `16000`
- clause train examples: `12000`
- max train/eval prompt intersection: `32`
- heldout register pairs: `[['R0', 'R3'], ['R3', 'R0']]`

## Heldout Program Instances

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| heldout_program_instances | 0.0909 | 1.0000 | 0.0000 | 4.09 |

## Heldout Program Template

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| heldout_template_merge_two | 0.0909 | 1.0000 | 0.0000 | 8.50 |

## MERGE_THREE

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| merge_three | 0.0000 | 0.2000 | 0.8000 | 8.50 |

## Rule Swap / Order Invariance

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| rule_swap | 0.5500 | 1.0000 | 0.0000 | 4.25 |
| order_invariance | 0.0909 | 1.0000 | 0.0000 | 2.64 |

## Distractor Rules

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| distractor_0 | 1.0000 | 1.0000 | 0.0000 | 6.00 |
| distractor_2 | 1.0000 | 1.0000 | 0.0000 | 6.00 |
| distractor_8 | 0.5455 | 0.5455 | 0.4545 | 3.50 |

## Rule Surface Generalization

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| surface_alternate | 0.0909 | 0.3939 | 0.6061 | 1.00 |

## Program-Ablation Tests

| split | final state exact | successful halt | invalid action rate | avg steps |
|---|---:|---:|---:|---:|
| program_removed | 0.0000 | 1.0000 | 0.0000 | 5.00 |
| shuffled_unrelated | 0.2500 | 1.0000 | 0.0000 | 5.00 |

## LM Action vs Policy Head if run

Policy head was not run because the primary LM-action interface is the required first test in M-20.

## Multi-Seed

Exploratory one-seed run only. The 3-seed gate is triggered only if heldout-program execution reaches 0.95.

## Generalization Matrix

| condition | split | final state exact | invalid action rate |
|---|---|---:|---:|
| seen state / seen program / seen registers / canonical / no distractors | seen_program_steps | 1.0000 | 0.0000 |
| 11..20 state / seen program | state_11_20 | 1.0000 | 0.0000 |
| 21..50 state / seen program | state_21_50 | 1.0000 | 0.0000 |
| 51..100 state / seen program | state_51_100 | 1.0000 | 0.0000 |
| identical state / counterfactual rules | counterfactual | 1.0000 | 0.0000 |
| seen state / heldout register permutation | heldout_register_permutation | 0.5909 | 0.0000 |
| seen state / heldout program instance | heldout_program_instances | 0.0909 | 0.0000 |
| seen state / heldout MERGE_TWO template | heldout_template_merge_two | 0.0909 | 0.0000 |
| 21..50 state / MERGE_TWO | merge_two_21_50 | 0.0000 | 0.0000 |
| 51..100 state / MERGE_TWO | merge_two_51_100 | 0.0000 | 0.0000 |
| 11..20 state / heldout MERGE_THREE template | merge_three | 0.0000 | 0.8000 |
| canonical / 2 distractors | distractor_2 | 1.0000 | 0.0000 |
| canonical / 8 distractors | distractor_8 | 0.5455 | 0.4545 |
| heldout structured rule surface | surface_alternate | 0.0909 | 0.6061 |

## Interpretation

OUTCOME B: seen programs generalize by trajectory length, but heldout programs fail.

## Recommended Next Architecture

Keep external state, but add rule/program pretraining and a stronger compositional DSL curriculum.

## Checks

- remote/local ruff + pytest: passed
- commit hash at report build: `08a5617`

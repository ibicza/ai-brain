# M-17.3 Position-Shift Invariance Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `e04be75`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Dataset Verification

- train_count: `9000`
- eval_count_per_op: `250`
- shifts: `[0, 1, 2, 4, 8, 16, 32]`
- contexts: `['canonical', 'task_prefix', 'step_prefix', 'state_prefix', 'previous_result', 'previous_operation', 'language_parse_prefix']`
- prompt_intersections: `0`
- M-17.1 checkpoints: `{'add': 'W:\\toolbox_IDEA\\programs\\IdeaProjects\\ai-brain\\runs\\m171_primitive_language\\primitive_add_scale_30000\\checkpoints\\step_020000.pt', 'sub': 'W:\\toolbox_IDEA\\programs\\IdeaProjects\\ai-brain\\runs\\m171_primitive_language\\primitive_sub_scale_30000\\checkpoints\\step_020000.pt'}`
- best_variant: `{'checkpoint': 'W:\\toolbox_IDEA\\programs\\IdeaProjects\\ai-brain\\runs\\m173_position_shift_invariance\\shape_32_content_prefix_0_8\\checkpoints\\step_008000.pt', 'name': 'shape_32_content_prefix_0_8', 'position_encoding': 'shifted_absolute', 'position_shift_max': 32, 'score': 0.3575}`

## APE Pure Position-Shift Curve

| offset | ADD | SUB |
|---:|---:|---:|
| 0 | 1.0000 | 1.0000 |
| 1 | 0.0000 | 0.0000 |
| 2 | 0.0000 | 0.0000 |
| 4 | 0.0000 | 0.0000 |
| 8 | 0.0000 | 0.0000 |
| 16 | 0.0000 | 0.0000 |
| 32 | 0.0000 | 0.0000 |

## Content-Prefix Shift Curve

| offset | ADD | SUB |
|---:|---:|---:|
| 0 | 1.0000 | 1.0000 |
| 1 | 0.0000 | 0.0000 |
| 2 | 0.0000 | 0.0000 |
| 4 | 0.0000 | 0.0000 |
| 8 | 0.0000 | 0.0000 |
| 16 | 0.0000 | 0.0000 |
| 32 | 0.0000 | 0.0000 |

## Position Method Comparison

| method | canonical | pure1 | pure2 | pure4 | pure8 | pure16 | pure32 | content1 | content2 | content4 | content8 | content16 | content32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ape_canonical | 0.8920 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| content_prefix_0_8 | 0.0920 | 0.0000 | 0.0660 | 0.0700 | 0.0640 | 0.0640 | 0.0000 | 0.0780 | 0.0700 | 0.0820 | 0.1000 | 0.0040 | 0.0020 |
| nope | 0.1240 | 0.1240 | 0.1240 | 0.1240 | 0.1240 | 0.1240 | 0.1240 | 0.0640 | 0.0520 | 0.0400 | 0.0320 | 0.0220 | 0.0080 |
| shape_32 | 0.0800 | 0.0660 | 0.0720 | 0.0780 | 0.0640 | 0.0860 | 0.0860 | 0.0820 | 0.0860 | 0.0480 | 0.0400 | 0.0360 | 0.0000 |
| shape_32_content_prefix_0_8 | 0.3660 | 0.4120 | 0.2940 | 0.5180 | 0.5500 | 0.6040 | 0.5860 | 0.2840 | 0.5480 | 0.5400 | 0.5940 | 0.5700 | 0.0100 |
| shape_64 | 0.4180 | 0.4500 | 0.4660 | 0.4700 | 0.4780 | 0.4460 | 0.4220 | 0.3540 | 0.3940 | 0.2060 | 0.0760 | 0.0520 | 0.0180 |
| shape_8 | 0.1960 | 0.1760 | 0.1940 | 0.2440 | 0.1840 | 0.0000 | 0.0040 | 0.1720 | 0.1640 | 0.1100 | 0.0000 | 0.0060 | 0.0200 |

## M-17.2 Context Retest

| context | final NEM |
|---|---:|
| canonical | 0.3660 |
| task_prefix | 0.4800 |
| step_prefix | 0.3280 |
| state_prefix | 0.0220 |
| previous_result | 0.2360 |
| previous_operation | 0.2500 |
| language_parse_prefix | 0.0240 |

## ADD_SUB Retest

Composition skipped: gate failed: neutral_min=0.2840, context_min=0.0220.

## Language Bridge Retest

| run | seen | heldout |
|---|---:|---:|
| language_ape | 1.0000 | 0.0000 |
| language_best_position | 0.9920 | 0.3140 |

## Multi-Seed Results

no variant reached neutral shift >= 0.90

## Relative Position Baseline

Deferred: M-17.3 implements the mandatory SHAPE-style shifted absolute positions and NoPE baseline. A true T5-style relative attention bias is intentionally not mixed into this diagnostic patch.

## Decision

OUTCOME D: no tested positional method made neutral content-prefix shifts robust enough for composition claims.
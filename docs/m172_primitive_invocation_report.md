# M-17.2 Primitive Invocation and Context Invariance

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `617c71f`
- device: `cuda:0` (NVIDIA GeForce RTX 3050 Laptop GPU)

## Dataset Verification

- train_count: `9000`
- eval_count: `250`
- contexts: `['canonical', 'task_prefix', 'step_prefix', 'state_prefix', 'previous_result', 'previous_operation', 'language_parse_prefix']`
- structured_contexts: `['structured_standalone', 'structured_step', 'structured_state', 'structured_previous_result', 'structured_previous_operation']`
- M-17.1 checkpoints: `{'add': 'W:\\toolbox_IDEA\\programs\\IdeaProjects\\ai-brain\\runs\\m171_primitive_language\\primitive_add_scale_30000\\checkpoints\\step_020000.pt', 'sub': 'W:\\toolbox_IDEA\\programs\\IdeaProjects\\ai-brain\\runs\\m171_primitive_language\\primitive_sub_scale_30000\\checkpoints\\step_020000.pt'}`
- prompt intersections including train probes: `{'composition': 250, 'context_aug\\add': 364, 'context_aug\\sub': 542, 'language': 0, 'structured\\add': 369, 'structured\\sub': 533}`
- heldout prompt intersections: `{'composition': 0, 'context_aug\\add': 0, 'context_aug\\sub': 0, 'language': 0, 'structured\\add': 0, 'structured\\sub': 0}`

## Context Invariance Matrix

| primitive | context | train | seen | unseen |
|---|---|---:|---:|---:|
| ADD | canonical | 1.0000 | 1.0000 | 1.0000 |
| ADD | task_prefix | 0.0160 | 0.0000 | 0.0000 |
| ADD | step_prefix | 0.0000 | 0.0120 | 0.0000 |
| ADD | state_prefix | 0.0000 | 0.0000 | 0.0000 |
| ADD | previous_result | 0.0000 | 0.0000 | 0.0000 |
| ADD | previous_operation | 0.0000 | 0.0000 | 0.0000 |
| ADD | language_parse_prefix | 0.0000 | 0.0040 | 0.0000 |
| SUB | canonical | 1.0000 | 1.0000 | 1.0000 |
| SUB | task_prefix | 0.0000 | 0.0000 | 0.0000 |
| SUB | step_prefix | 0.0000 | 0.0080 | 0.0080 |
| SUB | state_prefix | 0.0000 | 0.0000 | 0.0000 |
| SUB | previous_result | 0.0000 | 0.0000 | 0.0000 |
| SUB | previous_operation | 0.0000 | 0.0000 | 0.0000 |
| SUB | language_parse_prefix | 0.0000 | 0.0000 | 0.0000 |

## Neutral Prefix vs Semantic Prefix

| primitive | prefix | unseen final NEM |
|---|---|---:|
| ADD | neutral_0 | 1.0000 |
| ADD | neutral_1 | 0.0000 |
| ADD | neutral_2 | 0.0000 |
| ADD | neutral_4 | 0.0000 |
| ADD | neutral_8 | 0.0000 |
| ADD | semantic_previous_operation | 0.0000 |
| ADD | semantic_result | 0.0000 |
| ADD | semantic_step | 0.0000 |
| SUB | neutral_0 | 1.0000 |
| SUB | neutral_1 | 0.0000 |
| SUB | neutral_2 | 0.0000 |
| SUB | neutral_4 | 0.0000 |
| SUB | neutral_8 | 0.0000 |
| SUB | semantic_previous_operation | 0.0000 |
| SUB | semantic_result | 0.0000 |
| SUB | semantic_step | 0.0000 |

## Teacher-Forced Factorization

| probe | unseen final NEM |
|---|---:|
| B1 canonical | 1.0000 |
| B2 state + canonical SUB | 0.0000 |
| B3 state + STEP2 SUB | 0.0000 |
| B4 previous op + canonical SUB | 0.0000 |

## Context Augmentation

| run | split/context | final NEM |
|---|---|---:|
| canonical-only add | unseen previous_operation | 0.0000 |
| canonical-only sub | unseen previous_operation | 0.0000 |
| context_augmented_add | train_all | 0.6640 |
| context_augmented_add | unseen_canonical | 0.9200 |
| context_augmented_add | unseen_language_parse_prefix | 0.0000 |
| context_augmented_add | unseen_previous_operation | 0.0280 |
| context_augmented_sub | train_all | 0.6474 |
| context_augmented_sub | unseen_canonical | 0.8760 |
| context_augmented_sub | unseen_language_parse_prefix | 0.0000 |
| context_augmented_sub | unseen_previous_operation | 0.0040 |

## Structured Operation Representation

| representation | run | split/context | final NEM |
|---|---|---|---:|
| plain text | context_augmented_add | unseen_previous_operation | 0.0280 |
| plain text | context_augmented_sub | unseen_previous_operation | 0.0040 |
| structured OP | structured_op_add | train_all | 0.7584 |
| structured OP | structured_op_add | unseen_structured_previous_operation | 0.0000 |
| structured OP | structured_op_add | unseen_structured_standalone | 0.9400 |
| structured OP | structured_op_add | unseen_structured_state | 0.8440 |
| structured OP | structured_op_add | unseen_structured_step | 0.9520 |
| structured OP | structured_op_sub | train_all | 0.5160 |
| structured OP | structured_op_sub | unseen_structured_previous_operation | 0.0080 |
| structured OP | structured_op_sub | unseen_structured_standalone | 0.5800 |
| structured OP | structured_op_sub | unseen_structured_state | 0.6560 |
| structured OP | structured_op_sub | unseen_structured_step | 0.6240 |

## Composition Retest

Composition skipped: primitive invocation below 0.95 gate (min_context_score=0.0000).

## Optional Held-Out Composition

SUB_ADD held-out composition not tested because trained ADD_SUB did not run.

## Language -> Structured Bridge

| component | split | final/parse NEM | op | argA | argB |
|---|---|---:|---:|---:|---:|
| language -> structured parse | heldout | 0.1240 | 0.5320 | 0.5120 | 0.2040 |
| language -> structured parse | seen | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured parse -> arithmetic | add | 0.9280 | n/a | n/a | n/a |
| structured parse -> arithmetic | sub | 0.5760 | n/a | n/a | n/a |

## Decision

OUTCOME A: canonical ADD/SUB are high, but prefixed/wrapped contexts are lower, indicating contextual primitive invocation failure. OUTCOME E: language parsing into the shared structured primitive representation is a separate bottleneck.

## Next Milestone

Standardize operation representation and use a context-augmentation curriculum before broad composition.

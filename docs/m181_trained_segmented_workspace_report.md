# M-18.1 Trained Segmented Workspace Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `4aef4d9`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Dataset Verification

| item | value |
|---|---:|
| train_paired_irrelevant_count | 7200 |
| train_clean_fraction | 0.3333333333333333 |
| eval_clean_count | 120 |
| prompt_intersections | {'train_vs_clean_eval': 0} |

## Flat vs Isolated vs Workspace FIT

| steps | variant | clean overall | clean ADD | clean SUB | fit gate |
|---:|---|---:|---:|---:|---|
| 10000 | flat_relative | 0.9250 | 0.9500 | 0.9000 | fail |
| 10000 | isolated_relative | 0.8583 | 0.7833 | 0.9333 | fail |
| 10000 | workspace_relative | 0.9583 | 0.9667 | 0.9500 | fail |
| 20000 | flat_relative | 0.9583 | 0.9167 | 1.0000 | fail |
| 20000 | isolated_relative | 0.9583 | 0.9500 | 0.9667 | fail |
| 20000 | workspace_relative | 0.9917 | 0.9833 | 1.0000 | pass |
| 5000 | flat_relative | 0.6333 | 0.6167 | 0.6500 | fail |
| 5000 | isolated_relative | 0.8167 | 0.7500 | 0.8833 | fail |
| 5000 | workspace_relative | 0.9000 | 0.9000 | 0.9000 | fail |

## Distractor Robustness

| variant | clean | min<=16 | len32 min | len64 min | ADD clean | SUB clean |
|---|---:|---:|---:|---:|---:|---:|
| flat_relative | 0.9583 | 0.8333 | 0.8250 | 0.8083 | 0.9167 | 1.0000 |
| isolated_relative | 0.9583 | 0.9333 | 0.9500 | 0.9500 | 0.9500 | 0.9667 |
| workspace_relative | 0.9917 | 0.9833 | 0.9833 | 0.9833 | 0.9833 | 1.0000 |

## Relevant Context Retrieval

| run | overall | ADD | SUB |
|---|---:|---:|---:|
| workspace_relevant | 0.5000 | 0.9833 | 0.0167 |

## Oracle Chunk Selection

| run | overall | ADD | SUB |
|---|---:|---:|---:|
| workspace_relevant | 0.0000 | 0.0000 | 0.0000 |

## Variable Binding by Chain Depth and Distractor Count

| run | depth | distractors | final NEM |
|---|---:|---:|---:|
| workspace_relevant | 1 | 0 | 0.0000 |
| workspace_relevant | 1 | 1 | 0.0500 |
| workspace_relevant | 1 | 2 | 0.0000 |
| workspace_relevant | 1 | 4 | 0.0500 |
| workspace_relevant | 1 | 8 | 0.0000 |
| workspace_relevant | 2 | 0 | 0.0000 |
| workspace_relevant | 2 | 1 | 0.0000 |
| workspace_relevant | 2 | 2 | 0.0000 |
| workspace_relevant | 2 | 4 | 0.0000 |
| workspace_relevant | 2 | 8 | 0.0000 |
| workspace_relevant | 3 | 0 | 0.0000 |
| workspace_relevant | 3 | 1 | 0.0000 |
| workspace_relevant | 3 | 2 | 0.0000 |
| workspace_relevant | 3 | 4 | 0.0000 |
| workspace_relevant | 3 | 8 | 0.0000 |
| workspace_relevant | 4 | 0 | 0.0000 |
| workspace_relevant | 4 | 1 | 0.0000 |
| workspace_relevant | 4 | 2 | 0.0000 |
| workspace_relevant | 4 | 4 | 0.0000 |
| workspace_relevant | 4 | 8 | 0.0000 |

## Consistency Loss Ablation

skipped: consistency loss is only run after the base segmented model passes robustness/retrieval gates

## Hard-Distractor Mining Effect

skipped: hard-distractor mining is only run after an initial robust segmented model exists

## Learned Selector

skipped: learned selector requires oracle chunks >= .95 after relevant-context training

## Composition

skipped: ADD_SUB is only run after relevant retrieval and variable binding gates pass

## Recommended Core Context Architecture

OUTCOME A partial: training under workspace masks solves irrelevant distractor robustness, but oracle-access relevant context/chunk retrieval fails. Keep segmented workspace as the isolation architecture, but next work should target controlled retrieval/router training before learned selectors or composition.
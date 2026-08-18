# M-18.2 Workspace Retrieval Validation Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `47675aa`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## M-18.1 Bug Audit

M-18.1 trained `workspace_relevant` on `train_cases[:600]`. Because the case list was grouped as all ADD before all SUB, that training file contained ADD only. M-18.2 removes positional slicing and asserts ADD/SUB balance in every arithmetic-context train split.

The M-18.1 positive result is preserved as the starting point: the trained workspace model solved irrelevant distractor robustness. M-18.2 only revalidates relevant retrieval and binding.

## Balanced Dataset Verification

| item | value |
|---|---:|
| train_relevant_context_count | 2400 |
| train_relevant_add_count | 1200 |
| train_relevant_sub_count | 1200 |
| train_mixed_context_count | 3200 |
| train_variable_binding_count | 960 |
| prompt_intersections | {'train_relevant_vs_relevant_heldout_operands': 0, 'train_relevant_vs_relevant_seen': 0, 'train_relevant_vs_relevant_unseen': 0, 'train_relevant_vs_variable_binding': 0} |

## ADD/SUB Relevant Retrieval

| run | eval | overall | ADD | SUB | full NEM | false | empty | avg tok |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| from_robust | relevant_seen | 0.9437 | 0.9250 | 0.9625 | 0.9437 | 0.0000 | 0.0000 | 10.07 |
| from_robust | relevant_unseen | 0.9625 | 0.9750 | 0.9500 | 0.9625 | 0.0000 | 0.0000 | 10.12 |
| from_robust | relevant_heldout_operands | 0.1688 | 0.0000 | 0.3375 | 0.1688 | 0.0000 | 0.0000 | 9.78 |
| from_robust_plus5k | relevant_seen | 0.9563 | 1.0000 | 0.9125 | 0.9563 | 0.0000 | 0.0000 | 10.08 |
| from_robust_plus5k | relevant_unseen | 0.9812 | 1.0000 | 0.9625 | 0.9812 | 0.0000 | 0.0000 | 10.12 |
| from_robust_plus5k | relevant_heldout_operands | 0.2125 | 0.0000 | 0.4250 | 0.2125 | 0.0000 | 0.0000 | 9.85 |

## Retrieval-Only A/B/Pair

| run | eval | overall | A | B | pair | full NEM | false | empty | avg tok |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| from_robust | retrieval_only_seen | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 12.33 |
| from_robust | retrieval_only_unseen | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 12.33 |

## Oracle Chunk Selection

| run | junk chunks | overall | ADD | SUB |
|---|---:|---:|---:|---:|
| from_robust | 0 | 0.2000 | 0.2250 | 0.1750 |
| from_robust | 1 | 0.0688 | 0.0875 | 0.0500 |
| from_robust | 2 | 0.0875 | 0.1000 | 0.0750 |
| from_robust | 4 | 0.0813 | 0.1125 | 0.0500 |
| from_robust | 8 | 0.0625 | 0.0750 | 0.0500 |
| from_robust | 16 | 0.0375 | 0.0500 | 0.0250 |
| from_robust | 32 | 0.0187 | 0.0125 | 0.0250 |

## Mixed Relevant+Irrelevant Context

| run | eval | overall | ADD | SUB | full NEM | false | empty | avg tok |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| from_robust | clean | 0.9563 | 0.9750 | 0.9375 | 0.9563 | 0.0000 | 0.0000 | 10.12 |
| from_robust | irrelevant | 0.9625 | 0.9750 | 0.9500 | 0.9625 | 0.0000 | 0.0000 | 10.12 |
| from_robust | relevant | 0.4437 | 0.2375 | 0.6500 | 0.4437 | 0.0000 | 0.0000 | 10.14 |
| from_robust | mixed | 0.6438 | 0.6375 | 0.6500 | 0.6438 | 0.0000 | 0.0000 | 10.09 |

## Trained Variable Binding

| depth | distractors | final NEM |
|---:|---:|---:|
| 1 | 0 | 1.0000 |
| 1 | 1 | 1.0000 |
| 1 | 16 | 1.0000 |
| 1 | 2 | 1.0000 |
| 1 | 4 | 1.0000 |
| 1 | 8 | 0.8500 |
| 2 | 0 | 1.0000 |
| 2 | 1 | 1.0000 |
| 2 | 16 | 0.9000 |
| 2 | 2 | 1.0000 |
| 2 | 4 | 1.0000 |
| 2 | 8 | 0.9000 |
| 3 | 0 | 1.0000 |
| 3 | 1 | 1.0000 |
| 3 | 16 | 1.0000 |
| 3 | 2 | 1.0000 |
| 3 | 4 | 1.0000 |
| 3 | 8 | 0.9500 |
| 4 | 0 | 1.0000 |
| 4 | 1 | 1.0000 |
| 4 | 16 | 1.0000 |
| 4 | 2 | 1.0000 |
| 4 | 4 | 1.0000 |
| 4 | 8 | 0.7500 |

## Retention Matrix

| run | eval | overall | ADD | SUB | full NEM | false | empty | avg tok |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| replay_from_robust | clean | 0.9437 | 0.9500 | 0.9375 | 0.9437 | 0.0000 | 0.0000 | 10.11 |
| replay_from_robust | irrelevant | 0.9625 | 0.9750 | 0.9500 | 0.9625 | 0.0000 | 0.0000 | 10.11 |
| replay_from_robust | relevant | 0.1562 | 0.1875 | 0.1250 | 0.1562 | 0.0000 | 0.0000 | 10.14 |
| replay_from_robust | retrieval_only | 0.9563 | 0.0000 | 0.0000 | 0.9563 | 0.0000 | 0.0000 | 12.32 |
| replay_from_robust | variable_binding | 0.9333 | 0.0000 | 0.0000 | 0.9333 | 0.0000 | 0.0000 | 10.00 |

## Structured Workspace State

skipped: oracle chunks and direct relevant retrieval gates did not pass

## Learned Selector

skipped: learned selector is gated on oracle chunks and workspace state >= .95

## Composition

skipped: composition gate did not pass

## Recommended Architecture

OUTCOME D/E: the M-18.1 ADD/SUB asymmetry was a dataset bug, and retrieval-only A/B/pair is solved, but direct relevant arithmetic does not pass the strict per-op .95 gate. The bottleneck is the interface between retrieved context values and arithmetic execution, not raw value retrieval. Do not add a new architecture yet; next debug the workspace arithmetic interface and chunk access semantics.
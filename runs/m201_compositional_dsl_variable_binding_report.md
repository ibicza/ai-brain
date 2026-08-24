# M-20.1 Compositional DSL and Variable Binding

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## M-20 Starting Point

M-20 solved seen-program trajectory length with external exact state, but failed heldout register/program/template generalization.

## Structural Leakage Audit

| audit | value |
|---|---:|
| clause_overlap | 8 |
| exact_program_text_overlap | 8 |
| exact_prompt_overlap | 566 |
| heldout_template_overlap | 0 |
| logical_variable_pattern_overlap | 1 |
| normalized_ast_overlap | 5 |
| physical_binding_overlap | 8 |
| predicate_action_tuple_overlap | 9 |

## DSL Definition

Programs use logical variables (`A B C D`), compact structured clauses such as `NE A M A C`, a separate binding line (`A R0 B R1 ...`), a separate physical state line (`R0 NE ...`), and physical actions only after binding resolution.

## Binding Pretraining

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| binding_seen | 0.8889 | 0.0000 |
| binding_heldout | 0.8889 | 0.0000 |

## Predicate Semantics

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| predicate_seen | 1.0000 | 0.0000 |
| predicate_heldout | 1.0000 | 0.0000 |

## Action Semantics

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| action_seen | 1.0000 | 0.0000 |
| action_heldout_register_pairs | 1.0000 | 0.0000 |

## Single-Clause Composition

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| single_clause_heldout | 0.1458 | 0.0000 |

## Alpha-Renaming

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| alpha_renaming | 0.0625 | 0.0000 |

## Clause Selection Curriculum

Clause selection is represented by the primitive and curriculum one-step action decisions; a separate text clause-ID run was not launched because M-20 already showed clause IDs can fit seen programs.

## Clause Order Invariance

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| order_invariance | 0.9627 | 0.4688 | 0.0511 |

## Structured DSL

The curriculum model uses the structured DSL. The flat model uses the same underlying examples without staged prerequisite training.

## Program Grammar Pretraining

- primitive train examples: `12000`
- flat program examples: `14000`
- curriculum stage2 examples: `16000`

## Combination Coverage

| feature | unique |
|---|---:|
| bindings | 20 |
| predicate_action_tuples | 9 |
| program_families | 7 |
| templates | 5 |

## Heldout Register Bindings

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| heldout_binding | 0.8615 | 0.5540 | 0.0284 |

## Heldout Program Instances

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| heldout_program_instance | 0.5532 | 0.1061 | 0.0000 |

## Heldout Predicate Compositions

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| heldout_predicate_composition | 0.8489 | 0.6705 | 0.0000 |

## MERGE_TWO Curriculum

Training includes DRAIN components, two-clause switching, and non-MERGE multi-clause programs; exact MERGE_TWO AST is held out.

## Heldout MERGE_TWO

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| heldout_merge_two_seen | 0.6446 | 0.0871 | 0.0000 |
| heldout_merge_two_21_50 | 0.7875 | 0.0000 | 0.0000 |
| heldout_merge_two_51_100 | 0.8288 | 0.0000 | 0.0000 |

## Teacher-Forced Clause Diagnostic

| split | one-step accuracy | invalid rate |
|---|---:|---:|
| teacher_forced_merge_two | 0.6736 | 0.0000 |

## MERGE_THREE if gated

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| merge_three | 0.2183 | 0.0000 | 0.0000 |

## Program Ablations

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| program_removed | 0.6411 | 0.4792 | 0.1875 |
| wrong_program | 0.6129 | 0.6250 | 0.0000 |
| binding_swapped | 0.6129 | 0.3750 | 0.1458 |

## Distractor Clauses

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| distractor_8 | 0.6354 | 0.2784 | 0.0000 |
| distractor_16 | 0.5786 | 0.1534 | 0.0000 |

## Structural vs Surface Generalization

| split | one-step | closed-loop final | invalid rate |
|---|---:|---:|---:|
| surface_alternate | 0.8634 | 0.4318 | 0.0000 |

## Role Embeddings if gated

Not run; M-20.1 first tests plain token embeddings with explicit structured DSL.

## Policy Head if gated

Not run; action generation and binding composition are measured first.

## Flat vs Compositional Curriculum

| split | flat closed-loop | curriculum closed-loop |
|---|---:|---:|
| program_seen | 0.9280 | 0.5795 |
| heldout_binding | 0.6790 | 0.5540 |
| heldout_program_instance | 0.1212 | 0.1061 |
| heldout_merge_two_seen | 0.2955 | 0.0871 |

## Final Generalization Grid

| split | one-step | closed-loop | invalid |
|---|---:|---:|---:|
| program_seen | 0.8411 | 0.5795 | 0.0000 |
| program_length_21_50 | 0.8113 | 0.6667 | 0.0000 |
| program_length_51_100 | 0.6711 | 0.5833 | 0.0000 |
| heldout_binding | 0.8615 | 0.5540 | 0.0284 |
| heldout_program_instance | 0.5532 | 0.1061 | 0.0000 |
| heldout_predicate_composition | 0.8489 | 0.6705 | 0.0000 |
| heldout_merge_two_seen | 0.6446 | 0.0871 | 0.0000 |
| heldout_merge_two_21_50 | 0.7875 | 0.0000 | 0.0000 |
| heldout_merge_two_51_100 | 0.8288 | 0.0000 | 0.0000 |
| merge_three | 0.2183 | 0.0000 | 0.0000 |
| order_invariance | 0.9627 | 0.4688 | 0.0511 |
| distractor_8 | 0.6354 | 0.2784 | 0.0000 |
| distractor_16 | 0.5786 | 0.1534 | 0.0000 |
| surface_alternate | 0.8634 | 0.4318 | 0.0000 |

## Multi-Seed if gated

Exploratory one-seed run only. Multi-seed gate was not reached unless the report metrics exceed heldout-program/MERGE_TWO 0.90.

## Interpretation

OUTCOME E: factorized primitives do not compose reliably in this setup.

## Recommended Next Architecture

Current Transformer core did not acquire systematic program interpretation; test explicit hierarchical interpreter or policy-head decomposition.

## Checks

- remote/local ruff + pytest: passed
- commit hash at report build: `ea5c9d6`

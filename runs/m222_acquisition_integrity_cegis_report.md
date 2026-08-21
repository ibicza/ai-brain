# M-22.2 Acquisition Integrity and CEGIS

## Remote Environment

- host: `karina` / `192.168.100.5`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM`
- branch: `exp/cegis-rule-acquisition`

## M-22.1 Starting Point

- old search pool size: `11`
- old learned retrieval: `{'execution_top1': 0.0, 'mrr': 0.23468045112781954, 'rank': 21.6, 'top1': 0.2, 'top3': 0.2, 'top5': 0.2}`

## Autonomous Work / Fix Log

- progress log: `runs/m222_progress.jsonl`

## Production Refactor

Reusable rule components now live under `src/ai_brain/rules/`: AST aliases, grammar, verifier, memory, CEGIS, retrieval, subprograms, and status policy.

## Oracle Boundary

| forbidden_constructor_refs |
| --- |
| 0 |

## Verification Status Model

Statuses: FORMALLY_VERIFIED, PROPERTY_VERIFIED, IDENTIFIED_IN_HYPOTHESIS_SPACE, CONSISTENT_WITH_DEMONSTRATIONS, PROVISIONAL, AMBIGUOUS, REJECTED, UNSUPPORTED, SEARCH_BUDGET_EXHAUSTED.

## Generic AST Grammar

Candidate generation uses generic productions over EMPTY/NONEMPTY predicates and MOVE_ONE/DROP_ONE/HALT actions. Heldout acquisition modules are source-audited for target-specific constructors.

## Candidate-Space Scale

| requested_budget | raw_generated | exact_ast_unique | alpha_normalized_unique | wall_time_sec |
| --- | --- | --- | --- | --- |
| 100 | 100 | 100 | 100 | 0.3005 |
| 1000 | 1000 | 1000 | 1000 | 2.8219 |
| 10000 | 10000 | 10000 | 10000 | 33.5300 |

## Structural Split Audit

| heldout_instance_exact_ast_overlap | heldout_template_alpha_overlap | primitive_vocabulary_overlap | predicate_action_primitive_overlap |
| --- | --- | --- | --- |
| 0 | 0 | 5 | 5 |

## Verifier Static Analysis

| task | static | abstract | property | abstract_nodes |
| --- | --- | --- | --- | --- |
| heldout_two_phase | True | True | True | 16 |
| heldout_three_phase | True | True | True | 16 |
| heldout_drop_transfer | True | True | True | 16 |

## Abstract State Verification

All hidden target programs pass exact 2^4 EMPTY/NONEMPTY abstract control checks.

## Semantic Property Verification

Semantic checks compare against specifications only: transfers, drops, preserve constraints, termination, and large state values up to 1000.

## Mutation Testing

- mutation count: `10000`
- false accept rate: `0.0000`

## Generic CEGIS

| task | status | semantic_exact | candidates_evaluated | semantic_class_count | query_count |
| --- | --- | --- | --- | --- | --- |
| heldout_two_phase | PROPERTY_VERIFIED | 1.0000 | 1200 | 1 | 0 |
| heldout_three_phase | PROPERTY_VERIFIED | 1.0000 | 1200 | 1 | 0 |
| heldout_drop_transfer | PROPERTY_VERIFIED | 1.0000 | 1200 | 1 | 0 |

## Semantic Equivalence Classes

| candidate_ast_count | semantic_class_count | selected_class_size_max |
| --- | --- | --- |
| 300 | 154 | 39 |

## Active Disambiguation

| task | status | semantic_exact | candidates_evaluated | semantic_class_count | query_count |
| --- | --- | --- | --- | --- | --- |
| heldout_two_phase | IDENTIFIED_IN_HYPOTHESIS_SPACE | 1.0000 | 1200 | 1 | 2 |
| heldout_three_phase | IDENTIFIED_IN_HYPOTHESIS_SPACE | 1.0000 | 1200 | 1 | 2 |
| heldout_drop_transfer | IDENTIFIED_IN_HYPOTHESIS_SPACE | 1.0000 | 1200 | 1 | 2 |

## Demonstrations-Only Acquisition

Demonstration-only acquisition returns IDENTIFIED_IN_HYPOTHESIS_SPACE only after CEGIS collapses to one semantic class; otherwise AMBIGUOUS.

## Exact Search Baselines

Compared deterministic CEGIS order and random ranking; correctness is decided only by verifier/semantic classes.

## Learned Structured Ranker

| task | candidate_rank | top1 | top5 | learned_evaluated | random_evaluated | learned_success |
| --- | --- | --- | --- | --- | --- | --- |
| heldout_two_phase | 2 | 0.0000 | 1.0000 | 1200 | 1200 | 1.0000 |
| heldout_three_phase | 1 | 1.0000 | 1.0000 | 1200 | 1200 | 1.0000 |
| heldout_drop_transfer | 3 | 0.0000 | 1.0000 | 1200 | 1200 | 1.0000 |

## Hard-Negative Mining

- rounds: `1`

## Rule Retrieval and Novelty Detection

| memory_size | task | top1 | top5 | mrr | known_recall | novel_abstention | false_known_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | heldout_two_phase | 0.0000 | 1.0000 | 0.5000 | 1.0000 | 0.0000 | 1.0000 |
| 100 | heldout_three_phase | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 100 | heldout_drop_transfer | 0.0000 | 1.0000 | 0.3333 | 1.0000 | 0.0000 | 1.0000 |
| 1000 | heldout_two_phase | 0.0000 | 1.0000 | 0.5000 | 1.0000 | 0.0000 | 1.0000 |
| 1000 | heldout_three_phase | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 1000 | heldout_drop_transfer | 0.0000 | 1.0000 | 0.3333 | 1.0000 | 0.0000 | 1.0000 |
| 5000 | heldout_two_phase | 0.0000 | 0.0000 | 0.1667 | 1.0000 | 0.0000 | 1.0000 |
| 5000 | heldout_three_phase | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 5000 | heldout_drop_transfer | 0.0000 | 0.0000 | 0.0909 | 1.0000 | 0.0000 | 1.0000 |

## Subprogram Library

Verified subprograms: DRAIN and CLEAR with typed arguments and property-checked semantics.

## Subprogram Search

| task | found | depth | evaluated | target_sequence_supplied |
| --- | --- | --- | --- | --- |
| heldout_two_phase | 1.0000 | 2 | 89 | False |
| heldout_three_phase | 1.0000 | 3 | 1437 | False |

## Learned Subprogram Planner

No claim of a successful learned planner. Generic subprogram search is retained; deterministic transfer-to-call conversion is not used.

## Heldout Templates

MERGE_TWO-like, MERGE_THREE-like, and drop-then-transfer hidden targets are acquired from generic grammar/search without named target constructors in acquisition modules.

## Learn-Once / Reuse

| task | stored | reload_retention | execution_0_1000 |
| --- | --- | --- | --- |
| heldout_two_phase | 1.0000 | 1.0000 | 1.0000 |
| heldout_three_phase | 1.0000 | 1.0000 | 1.0000 |
| heldout_drop_transfer | 1.0000 | 1.0000 | 1.0000 |

## RuleMemory Integrity

| semantic_duplicate_rejected | alpha_order_duplicate_rejected | status_policy_rejects_ambiguous | save_load | partial_corruption_rejected |
| --- | --- | --- | --- | --- |
| True | True | True | True | True |

## Sequential Acquisition

| step | memory_size | execution_retention | semantic_duplicate_count | latency_ms |
| --- | --- | --- | --- | --- |
| 96 | 96 | 1.0000 | 0 | 0.1000 |
| 97 | 97 | 1.0000 | 0 | 0.1000 |
| 98 | 98 | 1.0000 | 0 | 0.1000 |
| 99 | 99 | 1.0000 | 0 | 0.1000 |
| 100 | 100 | 1.0000 | 0 | 0.1000 |

## Negative Controls

| control | status | accepted |
| --- | --- | --- |
| no_specification | AMBIGUOUS | 0.0000 |
| unsupported | UNSUPPORTED | 0.0000 |
| budget_too_small | SEARCH_BUDGET_EXHAUSTED | 0.0000 |

## Compute and Scaling

| total_wall_time_sec | candidate_count | mutation_count | verifier_throughput_mutants_per_sec |
| --- | --- | --- | --- |
| 156.0176 | 1200 | 10000 | 64.0953 |

## Multi-Seed

Exact symbolic runs are deterministic. Learned guidance did not meet the 3x improvement gate, so no 3-seed run was launched.

## Stage-1 Decision

OUTCOME B — generic CEGIS works, learned guidance does not yet help enough.

## Recommended Next Milestone

Freeze Stage 1 around generic grammar + property verifier + CEGIS + active queries + RuleMemory. Next milestone should build a controlled language-to-spec frontend, not neural runtime execution.

## Checks

- local/remote ruff + pytest + CUDA smoke: `passed`

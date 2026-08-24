# M-22.1 Oracle-Free Neural Rule Acquisition

## Remote Environment

- host: `karina` / `192.168.100.5`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM`
- branch: `exp/oracle-free-rule-acquisition`

## M-22 Neurality / Oracle Audit

See `docs/m221_m22_neurality_oracle_audit.md`. M-22 retrieval/search labels were renamed honestly: char-ngram retrieval, signature retrieval, heuristic-guided search, and oracle-target-present metrics are not called neural in M-22.1.

## Oracle Firewall

- target fields raise: `True`
- acquisition view: `spec_fields, demonstrations, rule_memory, allowed_sketches, primitive_vocabulary, search_budget`

## Benchmark Scale and Split Audit

| train_task_specs | heldout_program_instances | heldout_ast_templates | candidate_space_1e2 | candidate_space_1e3 | candidate_space_1e4 | heldout_sketches_absent |
| --- | --- | --- | --- | --- | --- | --- |
| 1000 | 200 | 100 | 120 | 1000 | 10000 | True |

## Heldout Sketch Removal

| exact_sketch_overlap | normalized_sketch_overlap | exact_ast_overlap_with_no_heldout_library | normalized_ast_overlap_with_no_heldout_library | primitive_operation_overlap | heldout_sketches_removed |
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 5 | True |

## Hard RuleMemory Distractors

- memory programs: `100`
- near-neighbor examples: `wrong variable, wrong action, missing clause, wrong destination, wrong halt`

## Learned Complete-Rule Retrieval

| top1 | top3 | top5 | mrr | execution_top1 |
| --- | --- | --- | --- | --- |
| 0.2000 | 0.2000 | 0.2000 | 0.2347 | 0.0000 |

## Novel-Rule Abstention

| threshold | known_rule_recall | novel_rule_abstention | false_known_rate |
| --- | --- | --- | --- |
| 8.6000 | 0.1500 | 1.0000 | 0.0000 |

## Learned Sketch Ranking

| top1 | top3 | top5 | heldout_detection |
| --- | --- | --- | --- |
| 0.2727 | 1.0000 | 1.0000 | 0.4545 |

## Typed Slot Filling

| slot_accuracy | whole_assignment_exact | ast_semantic_exact | verifier_acceptance | execution_exact |
| --- | --- | --- | --- | --- |
| 0.2333 | 0.0000 | 0.4000 | 0.0000 | 0.0000 |

## Learned Candidate Scorer

- parameter count: `37`
- differs from hand-written candidate_score: `True`

## Neural-Guided Search

| task | budget | status | success | candidates_evaluated |
| --- | --- | --- | --- | --- |
| merge_two | 10 | ACQUIRED | 1.0000 | 4 |
| merge_three | 10 | ACQUIRED | 1.0000 | 1 |
| merge_two | 100 | ACQUIRED | 1.0000 | 4 |
| merge_three | 100 | ACQUIRED | 1.0000 | 1 |
| merge_two | 1000 | ACQUIRED | 1.0000 | 4 |
| merge_three | 1000 | ACQUIRED | 1.0000 | 1 |
| merge_two | 10000 | ACQUIRED | 1.0000 | 4 |
| merge_three | 10000 | ACQUIRED | 1.0000 | 1 |
| merge_two | 100000 | ACQUIRED | 1.0000 | 4 |
| merge_three | 100000 | ACQUIRED | 1.0000 | 1 |

## Demonstration Induction Without Target Access

| task | demos | status | remaining | selected_correct | abstention |
| --- | --- | --- | --- | --- | --- |
| merge_two | 1 | AMBIGUOUS | 11 | 0.0000 | 1.0000 |
| merge_two | 2 | AMBIGUOUS | 4 | 0.0000 | 1.0000 |
| merge_two | 3 | AMBIGUOUS | 4 | 0.0000 | 1.0000 |
| merge_two | 5 | AMBIGUOUS | 4 | 0.0000 | 1.0000 |
| merge_three | 1 | AMBIGUOUS | 11 | 0.0000 | 1.0000 |
| merge_three | 2 | AMBIGUOUS | 3 | 0.0000 | 1.0000 |
| merge_three | 3 | AMBIGUOUS | 3 | 0.0000 | 1.0000 |
| merge_three | 5 | AMBIGUOUS | 3 | 0.0000 | 1.0000 |

## Active Disambiguation

| task | active_examples | active_remaining | active_success | random_examples | random_remaining | random_success |
| --- | --- | --- | --- | --- | --- | --- |
| merge_two | 2 | 1 | 1.0000 | 5 | 2 | 0.0000 |
| merge_three | 2 | 1 | 1.0000 | 2 | 1 | 1.0000 |

## Learned Subprogram Planner

| task | status | verified_execution | manual_sequence_supplied |
| --- | --- | --- | --- |
| merge_two | ACQUIRED | 1.0000 | False |
| merge_three | ACQUIRED | 1.0000 | False |

## Subprogram Search

| task | depth | evaluated | success |
| --- | --- | --- | --- |
| merge_two | 2 | 17 | 1.0000 |
| merge_three | 3 | 213 | 1.0000 |

## Specification Information Audit

| condition | class | neural_induction_claim |
| --- | --- | --- |
| canonical structured specification | FULLY_CONSTRUCTIVE | False |
| field-order permutation | FULLY_CONSTRUCTIVE | False |
| controlled paraphrased structured specification | CONSTRAINING | True |
| demonstrations only | BEHAVIORAL | True |
| partial specification + demonstrations | CONSTRAINING | True |

## Specification-Free Verifier

- uses target AST: `False`
- property conditions: `type validity, determinism, postconditions, preserve, empty, transfer, termination`

## Adversarial Verifier Test

| case | accepted | reason |
| --- | --- | --- |
| drops_second_source | 0.0000 | wrong_value_R2 |
| wrong_destination | 0.0000 | preserve_violation_D |
| preserves_one_source | 0.0000 | not_empty_B |
| wrong_halt_condition | 0.0000 | not_empty_B |
- false verified program rate: `0.0000`

## True Learn-Once / Reuse

| task | acquisition_success | verification_success | storage_success | reuse_execution_min |
| --- | --- | --- | --- | --- |
| merge_two | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Sequential RuleMemory Growth

| step | memory_size | execution_retention | semantic_duplicates |
| --- | --- | --- | --- |
| 1 | 1 | 1.0000 | 0 |
| 2 | 2 | 1.0000 | 1 |
| 3 | 3 | 1.0000 | 1 |
| 4 | 4 | 1.0000 | 1 |
| 5 | 5 | 1.0000 | 2 |
| 6 | 6 | 1.0000 | 3 |
| 7 | 7 | 1.0000 | 4 |
| 8 | 8 | 1.0000 | 5 |
| 9 | 9 | 1.0000 | 6 |
| 10 | 10 | 1.0000 | 6 |

## Multi-Seed

Exploratory seed only. The learned components are lightweight linear rankers; exact symbolic methods remain deterministic.

## Interpretation

OUTCOME C: subprogram planning is the strongest oracle-free representation; use verified calls plus exact execution.

## Recommended Stage-1 Boundary

Use exact RuleMemory/interpreter as the safety boundary. Learned retrieval/scoring may order candidates, but only property verification plus ambiguity handling can write a rule. Fully constructive specs are an exact compiler upper bound, not evidence of neural induction.

## Checks

- local/remote ruff + pytest + CUDA smoke: `passed`

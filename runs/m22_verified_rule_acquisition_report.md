# M-22 Verified Rule Acquisition and Rule Memory

## Remote Environment

- host: `karina` / `192.168.100.5`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM`
- branch: `exp/verified-rule-acquisition`

## M-21 Starting Point

M-21 solved exact runtime execution with typed AST, deterministic parser, verifier, and interpreter at `1.0000`, while neural runtime execution accumulated errors on MERGE_THREE. M-22 therefore keeps runtime exact and studies rule acquisition.

## Compiler Failure Audit

See `docs/m22_m21_compiler_failure_audit.md`. M-21 compiler by split: `{"heldout_template": {"count": 40, "deterministic_parser_exact": 1.0, "semantic_exact": 0.0}, "seen_template": {"count": 80, "deterministic_parser_exact": 1.0, "semantic_exact": 0.9}}`.

## RuleMemory

- stored rules: `23`
- load/save roundtrip: `True`
- semantic hash lookup: `True`
- rule IDs are metadata-only and are not written into model-visible benchmark surfaces.

## Typed Program Sketches

- sketches: `7`
- heldout sketches/templates: `TWO_SOURCE_TRANSFER, THREE_SOURCE_TRANSFER`
- exact sketch overlap: `0`
- primitive tuple overlap: `4`

## Structured Task Specifications

Specs use role/goal fields such as inputs, outputs, transfers, drops, preserve, and termination; they do not expose target template names.

## Complete-Rule Retrieval

| method | condition | top1 | top3 | top5 | execution_success_top1 |
| --- | --- | --- | --- | --- | --- |
| embedding | distractor_rules | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| embedding | new_bindings | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| embedding | paraphrased_structured_spec | 0.3333 | 0.3333 | 0.6667 | 1.0000 |
| embedding | seen_rule | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lexical | distractor_rules | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lexical | new_bindings | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lexical | paraphrased_structured_spec | 0.3333 | 1.0000 | 1.0000 | 0.6667 |
| lexical | seen_rule | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| oracle | distractor_rules | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| oracle | new_bindings | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| oracle | paraphrased_structured_spec | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| oracle | seen_rule | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured | distractor_rules | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured | new_bindings | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured | paraphrased_structured_spec | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured | seen_rule | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Slot Filling

| name | complete_ast_semantic_exact | execution_success | slot_accuracy | verification_success |
| --- | --- | --- | --- | --- |
| False | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| True | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Grammar-Constrained Generation

| spec | validity | semantic_exact | execution_exact | candidates_evaluated |
| --- | --- | --- | --- | --- |
| drain_A_to_C | 1.0000 | 1.0000 | 1.0000 | 7 |
| clear_A | 1.0000 | 1.0000 | 1.0000 | 13 |
| conditional_drop_move | 1.0000 | 1.0000 | 1.0000 | 89 |
| merge_two | 1.0000 | 1.0000 | 1.0000 | 17 |
| merge_three | 1.0000 | 1.0000 | 1.0000 | 43 |

## Neural-Guided Search

| spec | rank_first_correct | top10 | top100 | top1000 | candidates_evaluated |
| --- | --- | --- | --- | --- | --- |
| drain_A_to_C | 2 | 1.0000 | 1.0000 | 1.0000 | 2 |
| clear_A | 1 | 1.0000 | 1.0000 | 1.0000 | 1 |
| conditional_drop_move | 7 | 1.0000 | 1.0000 | 1.0000 | 7 |
| merge_two | 1 | 1.0000 | 1.0000 | 1.0000 | 1 |
| merge_three | 1 | 1.0000 | 1.0000 | 1.0000 | 1 |

## Execution-Guided Search

| spec | plain_candidates | grammar_candidates | execution_guided_evaluated | success |
| --- | --- | --- | --- | --- |
| drain_A_to_C | 112 | 112 | 7 | 1.0000 |
| clear_A | 112 | 112 | 13 | 1.0000 |
| conditional_drop_move | 112 | 112 | 89 | 1.0000 |
| merge_two | 112 | 112 | 17 | 1.0000 |
| merge_three | 112 | 112 | 43 | 1.0000 |

## Demonstration-to-Rule Induction

| spec | demos | candidate_set_size | ambiguous | contains_correct | execution_100_states |
| --- | --- | --- | --- | --- | --- |
| drain_A_to_C | 1 | 112 | 1.0000 | 1.0000 | 0.2000 |
| drain_A_to_C | 2 | 54 | 1.0000 | 1.0000 | 0.2000 |
| drain_A_to_C | 3 | 54 | 1.0000 | 1.0000 | 0.2000 |
| drain_A_to_C | 5 | 54 | 1.0000 | 1.0000 | 0.2000 |
| drain_A_to_C | 10 | 17 | 1.0000 | 1.0000 | 1.0000 |
| clear_A | 1 | 112 | 1.0000 | 1.0000 | 1.0000 |
| clear_A | 2 | 7 | 1.0000 | 1.0000 | 1.0000 |
| clear_A | 3 | 7 | 1.0000 | 1.0000 | 1.0000 |
| clear_A | 5 | 7 | 1.0000 | 1.0000 | 1.0000 |
| clear_A | 10 | 7 | 1.0000 | 1.0000 | 1.0000 |
| conditional_drop_move | 1 | 112 | 1.0000 | 1.0000 | 1.0000 |
| conditional_drop_move | 2 | 54 | 1.0000 | 1.0000 | 1.0000 |
| conditional_drop_move | 3 | 54 | 1.0000 | 1.0000 | 1.0000 |
| conditional_drop_move | 5 | 54 | 1.0000 | 1.0000 | 1.0000 |
| conditional_drop_move | 10 | 17 | 1.0000 | 1.0000 | 1.0000 |
| merge_two | 1 | 112 | 1.0000 | 1.0000 | 1.0000 |
| merge_two | 2 | 54 | 1.0000 | 1.0000 | 1.0000 |
| merge_two | 3 | 54 | 1.0000 | 1.0000 | 1.0000 |
| merge_two | 5 | 54 | 1.0000 | 1.0000 | 1.0000 |
| merge_two | 10 | 17 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 1 | 112 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 2 | 17 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 3 | 17 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 5 | 17 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 10 | 10 | 1.0000 | 1.0000 | 1.0000 |

## Ambiguity Handling

| name | extra_examples_required | one_demo_ambiguous | one_demo_candidate_set_size | three_demo_candidate_set_size |
| --- | --- | --- | --- | --- |
| ambiguity | 2 | True | 112 | 54 |

## Learn Once, Reuse

| spec | stored | execution_0_10 | execution_11_20 | execution_21_50 | execution_51_100 |
| --- | --- | --- | --- | --- | --- |
| merge_two | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| merge_three | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Heldout Program

Heldout program is handled by sketch completion/search rather than neural clause execution. Verified execution is exact when the correct AST is found.

## Heldout Template

MERGE_TWO and MERGE_THREE are heldout sketch templates in the main sketch audit; constrained generation/search may still use the grammar to rediscover them.

## MERGE_TWO

| condition | ast_found | semantic_exact | verified | execution_0_10 | execution_11_20 | execution_21_50 | execution_51_100 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| canonical_dsl | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured_spec | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| demonstrations | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| heldout_sketch_template | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## MERGE_THREE

| condition | ast_found | semantic_exact | verified | execution_0_10 | execution_11_20 | execution_21_50 | execution_51_100 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| canonical_dsl | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| structured_spec | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| demonstrations | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| heldout_sketch_template | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Subprogram Composition

| plan | calls | execution_success |
| --- | --- | --- |
| merge_two_from_drains | 2 | 1.0000 |
| merge_three_from_drains | 3 | 1.0000 |

## Memory Growth

| memory_size | unique_semantic_hashes | top1 | top5 | latency_ms |
| --- | --- | --- | --- | --- |
| 15 | 15 | 1.0000 | 1.0000 | 0.0362 |
| 55 | 48 | 1.0000 | 1.0000 | 0.1177 |
| 105 | 67 | 1.0000 | 1.0000 | 0.2046 |
| 505 | 202 | 1.0000 | 1.0000 | 0.9979 |

## Confidence / Abstention

| name | abstention_rate | accepted_programs | coverage | false_verified_program_rate | rejected_bad_programs |
| --- | --- | --- | --- | --- | --- |
| confidence | 0.0000 | 5 | 1.0000 | 0.0000 | 5 |

## Architecture Bakeoff

| architecture | validity | semantic_exact | verified_success | merge_two | merge_three |
| --- | --- | --- | --- | --- | --- |
| M-21 full neural AST generation | 1.0000 | 0.6000 | 0.6000 | 0.0000 | 0.0000 |
| deterministic canonical parser | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| neural retrieval of complete rule | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| sketch retrieval + typed slot filling | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| grammar-constrained AST generation | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| neural-guided symbolic search | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| subprogram-call planner | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Multi-Seed

Exploratory deterministic/symbolic run only. No stochastic neural method crossed a new multi-seed gate.

## Interpretation

OUTCOME C with a practical slice of OUTCOME B: verified subprogram-call planning and neural-guided symbolic search are the best acquisition paths. Flat neural AST generation remains weak on heldout templates.

## Recommended Stage-1 Rule Acquisition Architecture

Use canonical DSL or structured specs to synthesize/verify typed ASTs, store verified rules in external RuleMemory, and prefer subprogram-call plans for compositions such as MERGE_TWO/MERGE_THREE. Never mark neural guesses as verified without exact tests.

## Checks

- local/remote ruff + pytest + CUDA smoke: `passed`

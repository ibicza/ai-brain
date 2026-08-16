# M-17.1 Primitive + Language Stabilization

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `317e8cc`
- device: `cuda:0` (NVIDIA GeForce RTX 3050 Laptop GPU)

## Primitive Data Scale

| task | scale | step | train | seen | unseen | buckets |
|---|---:|---:|---:|---:|---:|---|
| add | 3000 | 5000 | 0.8920 | 0.9080 | 0.9060 | carry_bucket(final_carry:0.8263, no_carry:0.9401, units_carry:0.9518); output_length(2_digit:0.9459, 3_digit:0.8263) |
| add | 10000 | 5000 | 0.9600 | 0.9620 | 0.9280 | carry_bucket(final_carry:0.8880, no_carry:0.9680); output_length(2_digit:0.9680, 3_digit:0.8880) |
| add | 10000 | 10000 | 0.9400 | 0.9360 | 0.9540 | carry_bucket(final_carry:0.9600, no_carry:0.9480); output_length(2_digit:0.9480, 3_digit:0.9600) |
| add | 30000 | 5000 | 0.9420 | 0.9560 | 0.9300 | carry_bucket(final_carry:0.9320, no_carry:0.9280); output_length(2_digit:0.9280, 3_digit:0.9320) |
| add | 30000 | 10000 | 0.9660 | 0.9600 | 0.9300 | carry_bucket(final_carry:0.8680, no_carry:0.9920); output_length(2_digit:0.9920, 3_digit:0.8680) |
| add | 30000 | 15000 | 0.9300 | 0.9440 | 0.9340 | carry_bucket(final_carry:0.8920, no_carry:0.9760); output_length(2_digit:0.9760, 3_digit:0.8920) |
| add | 30000 | 20000 | 1.0000 | 1.0000 | 1.0000 | carry_bucket(final_carry:1.0000, no_carry:1.0000); output_length(2_digit:1.0000, 3_digit:1.0000) |
| compare_numbers | 3000 | 5000 | 0.9980 | 0.9980 | 0.9960 | relation(GT:1.0000, LT:0.9920) |
| compare_sum | 3000 | 5000 | 0.9120 | 0.9180 | 0.8440 | relation(EQUAL:0.9222, LEFT:0.7365, RIGHT:0.8735) |
| compare_sum | 10000 | 5000 | 0.9420 | 0.9080 | 0.8940 | relation(EQUAL:0.9162, LEFT:0.9461, RIGHT:0.8193) |
| compare_sum | 10000 | 10000 | 0.9020 | 0.9040 | 0.8780 | relation(EQUAL:0.8144, LEFT:0.8743, RIGHT:0.9458) |
| compare_sum | 30000 | 5000 | 0.9020 | 0.9360 | 0.9080 | relation(EQUAL:0.8982, LEFT:0.8922, RIGHT:0.9337) |
| compare_sum | 30000 | 10000 | 0.9360 | 0.9600 | 0.9320 | relation(EQUAL:0.9701, LEFT:0.9401, RIGHT:0.8855) |
| compare_sum | 30000 | 15000 | 0.9380 | 0.9320 | 0.9040 | relation(EQUAL:0.9042, LEFT:0.8623, RIGHT:0.9458) |
| compare_sum | 30000 | 20000 | 0.9500 | 0.9500 | 0.9100 | relation(EQUAL:0.9401, LEFT:0.8443, RIGHT:0.9458) |
| missing_addend | 3000 | 5000 | 0.8920 | 0.8620 | 0.8700 | answer_range(10_49:0.8000, 50_99:0.9400); borrow_bucket(borrow:0.9520, no_borrow:0.7880); output_length(2_digit:0.8700) |
| missing_addend | 10000 | 5000 | 0.7940 | 0.7640 | 0.7800 | answer_range(10_49:0.8560, 50_99:0.7040); borrow_bucket(borrow:0.7600, no_borrow:0.8000); output_length(2_digit:0.7800) |
| missing_addend | 10000 | 10000 | 0.9220 | 0.9200 | 0.9160 | answer_range(10_49:0.8640, 50_99:0.9680); borrow_bucket(borrow:0.9560, no_borrow:0.8760); output_length(2_digit:0.9160) |
| missing_addend | 30000 | 5000 | 0.8520 | 0.8480 | 0.8000 | answer_range(10_49:0.7800, 50_99:0.8200); borrow_bucket(borrow:0.7760, no_borrow:0.8240); output_length(2_digit:0.8000) |
| missing_addend | 30000 | 10000 | 0.9700 | 0.9640 | 0.9460 | answer_range(10_49:0.9160, 50_99:0.9760); borrow_bucket(borrow:0.9480, no_borrow:0.9440); output_length(2_digit:0.9460) |
| missing_addend | 30000 | 15000 | 0.9920 | 0.9920 | 0.9920 | answer_range(10_49:0.9960, 50_99:0.9880); borrow_bucket(borrow:0.9920, no_borrow:0.9920); output_length(2_digit:0.9920) |
| missing_addend | 30000 | 20000 | 1.0000 | 1.0000 | 0.9980 | answer_range(10_49:1.0000, 50_99:0.9960); borrow_bucket(borrow:1.0000, no_borrow:0.9960); output_length(2_digit:0.9980) |
| sub | 3000 | 5000 | 0.9220 | 0.9100 | 0.8340 | borrow_bucket(borrow:0.8800, no_borrow:0.7880); output_length(2_digit:0.8340) |
| sub | 10000 | 5000 | 0.9620 | 0.9640 | 0.8720 | borrow_bucket(borrow:0.9000, no_borrow:0.8440); output_length(2_digit:0.8720) |
| sub | 10000 | 10000 | 0.9140 | 0.9100 | 0.8260 | borrow_bucket(borrow:0.8920, no_borrow:0.7600); output_length(2_digit:0.8260) |
| sub | 30000 | 5000 | 0.9100 | 0.9280 | 0.8860 | borrow_bucket(borrow:0.9240, no_borrow:0.8480); output_length(2_digit:0.8860) |
| sub | 30000 | 10000 | 0.9660 | 0.9520 | 0.9220 | borrow_bucket(borrow:0.8920, no_borrow:0.9520); output_length(2_digit:0.9220) |
| sub | 30000 | 15000 | 0.9520 | 0.9520 | 0.9400 | borrow_bucket(borrow:0.9680, no_borrow:0.9120); output_length(2_digit:0.9400) |
| sub | 30000 | 20000 | 1.0000 | 1.0000 | 1.0000 | borrow_bucket(borrow:1.0000, no_borrow:1.0000); output_length(2_digit:1.0000) |

## Stabilized Single Primitives

| task | best variant | train | seen | unseen |
|---|---|---:|---:|---:|
| add | 30000_20000 | 1.0000 | 1.0000 | 1.0000 |
| compare_numbers | 3000_5000 | 0.9980 | 0.9980 | 0.9960 |
| compare_sum | 30000_10000 | 0.9360 | 0.9600 | 0.9320 |
| missing_addend | 30000_20000 | 1.0000 | 1.0000 | 0.9980 |
| sub | 30000_20000 | 1.0000 | 1.0000 | 1.0000 |

## Symbolic Staged Retention

| stage | add | sub | missing_addend | compare_numbers | compare_sum |
|---|---:|---:|---:|---:|---:|
| symbolic_staged_1_stage1_add_sub | 0.9060 | 0.8260 | n/a | n/a | n/a |
| symbolic_staged_2_stage2_missing | 0.9600 | 0.8500 | 0.7600 | n/a | n/a |
| symbolic_staged_3_stage3_compare_numbers | 0.9640 | 0.9460 | 0.7240 | 0.9880 | n/a |
| symbolic_staged_4_stage4_compare_sum | 0.9640 | 0.9460 | 0.9220 | 0.9540 | 0.7860 |

## Language Operation Classification

| run | seen | paraphrase | lexical | heldout op buckets |
|---|---:|---:|---:|---|
| language_op_templates_10 | 0.7780 | 0.3720 | 0.7000 | n/a |
| language_op_templates_2 | 0.3320 | 0.2900 | 0.3140 | n/a |
| language_op_templates_20 | 1.0000 | 0.3340 | 0.6480 | n/a |
| language_op_templates_5 | 0.4040 | 0.2640 | 0.3640 | n/a |

## Language Structured Parsing

| split | op | argA | argB | full parse |
|---|---:|---:|---:|---:|
| lexical | 0.5900 | 0.2460 | 0.0620 | 0.0200 |
| paraphrase | 0.3560 | 0.0580 | 0.0780 | 0.0000 |
| seen | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Language Execution

| split | parse correct | final given parse | full final |
|---|---:|---:|---:|
| lexical | 0.0320 | 0.1875 | 0.0160 |
| paraphrase | 0.0100 | 0.2000 | 0.0180 |
| seen | 0.9800 | 0.0878 | 0.0860 |
| teacher_forced | 0.0000 | n/a | 0.0000 |

## Template Diversity Ablation

| run | seen | paraphrase | lexical | heldout op buckets |
|---|---:|---:|---:|---|
| language_op_templates_10 | 0.7780 | 0.3720 | 0.7000 | n/a |
| language_op_templates_2 | 0.3320 | 0.2900 | 0.3140 | n/a |
| language_op_templates_20 | 1.0000 | 0.3340 | 0.6480 | n/a |
| language_op_templates_5 | 0.4040 | 0.2640 | 0.3640 | n/a |

## Symbolic + Language Retention

| split | score |
|---|---:|
| add_unseen | 0.0500 |
| compare_numbers_unseen | 0.8940 |
| compare_sum_unseen | 0.7860 |
| missing_addend_unseen | 0.0420 |
| state_exec_paraphrase | 0.0020 |
| state_op_paraphrase | 0.0300 |
| state_parse_paraphrase | 0.0000 |
| sub_unseen | 0.0460 |

## Minimal ADD_SUB Retest

| split | final | step1 | step2 |
|---|---:|---:|---:|
| seen | 0.0000 | 0.9520 | 0.0040 |
| teacher_forced | 0.0120 | 0.0000 | 0.0000 |
| train | 0.0000 | 0.9520 | 0.0040 |
| unseen | 0.0000 | 0.9260 | 0.0020 |

## Dataset Notes

- 30k primitive scale uses balanced repeat coverage over finite two-digit candidate spaces when unique prompts are exhausted.
- STATE templates are split into train-pool families 0-19, paraphrase-heldout 20-24, and lexical-heldout 25-29.
- language verification: `{'op_eval_lexical': 0, 'op_eval_paraphrase': 0, 'op_eval_seen': 0, 'parse_eval_lexical': 0, 'parse_eval_paraphrase': 0, 'parse_eval_seen': 0}`

## Decision

OUTCOME F: symbolic primitives are mostly stabilized, but not all hit the target. Weak symbolic tasks: compare_sum. OUTCOME E: language OP/PARSE does not generalize enough on held-out templates. OUTCOME D: language-to-execution remains weak even when evaluated separately. OUTCOME B: ADD_SUB composition remains weak (unseen final=0.0000, step1=0.9260, step2=0.0020).

## Next Milestone

Investigate working-memory/state-transition bottleneck with teacher-forced traces.

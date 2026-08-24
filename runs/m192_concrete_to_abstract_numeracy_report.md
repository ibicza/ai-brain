# M-19.2 Concrete-to-Abstract Numeracy

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## Research Hypotheses

Concept-first numeracy tests whether quantity/cardinality/place-value curricula produce more transferable addition behavior than direct symbolic addition or M-19.1 rule-style traces.

## Dataset / Leakage Audit

| area | item | count | task types | prompt intersection max |
|---|---|---:|---|---:|
| curricula | concrete_sequential | 9000 | {'m192.add.concrete_small': 1200, 'm192.add.structured_no_regroup': 1318, 'm192.add.structured_regroup': 882, 'm192.add.symbolic': 4093, 'm192.base10.grouping': 30, 'm192.base10.ungrouping': 30, 'm192.count': 132, 'm192.invariance.more_less': 500, 'm192.invariance.same_count': 500, 'm192.make': 66, 'm192.place_value.seen': 90, 'm192.successor.concrete': 60, 'm192.successor.symbolic': 99} | 0 |
| curricula | direct_compute_matched | 9000 | {'m192.add.symbolic': 9000} | 0 |
| curricula | direct_symbolic | 9000 | {'m192.add.symbolic': 9000} | 0 |
| curricula | interleaved_concrete_symbolic | 9000 | {'m192.add.concrete_small': 1200, 'm192.add.structured_no_regroup': 2506, 'm192.add.structured_regroup': 1704, 'm192.add.symbolic': 2659, 'm192.base10.grouping': 30, 'm192.base10.ungrouping': 30, 'm192.compare.more_less': 400, 'm192.count': 132, 'm192.place_value.seen': 180, 'm192.successor.concrete': 60, 'm192.successor.symbolic': 99} | 0 |
| curricula | paired_representation | 9000 | {'m192.add.structured_no_regroup': 1318, 'm192.add.structured_regroup': 882, 'm192.add.symbolic': 4718, 'm192.base10.grouping': 30, 'm192.base10.ungrouping': 30, 'm192.count': 132, 'm192.paired.concrete_symbolic_add': 900, 'm192.paired.quantity_symbol': 900, 'm192.place_value.seen': 90} | 0 |
| curricula | symbolic_concept_first | 9000 | {'m192.add.structured_no_regroup': 1596, 'm192.add.structured_regroup': 1106, 'm192.add.symbolic': 5000, 'm192.compare.more_less': 800, 'm192.place_value.seen': 180, 'm192.successor.concrete': 120, 'm192.successor.symbolic': 198} | 0 |
| eval_splits | add_2digit_no_regroup | 160 | {'m192.add.symbolic': 160} | 0 |
| eval_splits | add_2digit_regroup | 160 | {'m192.add.symbolic': 160} | 0 |
| eval_splits | base10_grouping | 30 | {'m192.base10.grouping': 30} | 0 |
| eval_splits | base10_ungrouping | 30 | {'m192.base10.ungrouping': 30} | 0 |
| eval_splits | count_heldout_format | 66 | {'m192.count': 66} | 0 |
| eval_splits | count_heldout_object | 33 | {'m192.count': 33} | 0 |
| eval_splits | count_seen | 33 | {'m192.count': 33} | 0 |
| eval_splits | length_3 | 80 | {'m192.add.symbolic': 80} | 0 |
| eval_splits | length_4 | 80 | {'m192.add.symbolic': 80} | 0 |
| eval_splits | length_5 | 80 | {'m192.add.symbolic': 80} | 0 |
| eval_splits | length_6 | 80 | {'m192.add.symbolic': 80} | 0 |
| eval_splits | length_8 | 80 | {'m192.add.symbolic': 80} | 0 |
| eval_splits | more_less | 120 | {'m192.invariance.more_less': 120} | 0 |
| eval_splits | place_value | 90 | {'m192.place_value.seen': 90} | 0 |
| eval_splits | place_value_holdout | 45 | {'m192.place_value.holdout': 45} | 0 |
| eval_splits | pure_symbolic_clean_id | 240 | {'m192.add.symbolic': 240} | 0 |
| eval_splits | pure_symbolic_digit_pair_ood | 240 | {'m192.add.symbolic': 240} | 0 |
| eval_splits | pure_symbolic_range_ood | 160 | {'m192.add.symbolic': 160} | 0 |
| eval_splits | same_count | 120 | {'m192.invariance.same_count': 120} | 0 |
| eval_splits | small_concrete_add | 160 | {'m192.add.concrete_small': 160} | 0 |
| eval_splits | small_symbolic_add | 66 | {'m192.add.symbolic': 66} | 0 |
| eval_splits | successor_concrete | 30 | {'m192.successor.concrete_heldout': 30} | 0 |
| eval_splits | successor_symbolic | 10 | {'m192.successor.symbolic': 10} | 0 |
| bridge_sets | symbolic_add_0 | 0 | {} | 0 |
| bridge_sets | symbolic_add_100 | 800 | {'m192.add.symbolic': 800} | 0 |
| bridge_sets | symbolic_add_20 | 300 | {'m192.add.symbolic': 300} | 0 |
| diagnostic_sets | count_invariance | 8000 | {'m192.count': 1000, 'm192.invariance.more_less': 3500, 'm192.invariance.same_count': 3500} | 0 |
| diagnostic_sets | count_only | 6000 | {'m192.count': 6000} | 0 |

## Tokenization of Concrete Quantities

| family | max count | monotonic | aggregate leak rows |
|---|---:|---|---:|
| # | 10 | True | 0 |
| @ | 10 | True | 0 |
| A | 10 | True | 0 |
| K | 10 | True | 0 |
| OBJ | 10 | True | 0 |
| Q | 10 | True | 0 |
| STAR | 10 | True | 0 |
| X | 10 | True | 0 |
| Z | 10 | True | 0 |

## Cardinality Results

| group | count_seen | count_heldout_object | count_heldout_format |
|---|---:|---:|---:|
| direct_symbolic | 0.0000 | 0.0000 | 0.0000 |
| direct_compute_matched | 0.0000 | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.0000 | 0.0000 | 0.0000 |
| concrete_sequential | 0.6061 | 0.4545 | 0.1364 |
| interleaved_concrete_symbolic | 0.3636 | 0.3636 | 0.1212 |
| paired_representation | 0.3636 | 0.2727 | 0.1515 |

## Cardinality Diagnostics

| group | count_seen | count_heldout_object | count_heldout_format | same_count | more_less |
|---|---:|---:|---:|---:|---:|
| diagnostic_count_only | 0.9091 | 0.6667 | 0.1818 | 0.0000 | 0.0000 |
| diagnostic_count_invariance | 0.9091 | 0.6667 | 0.3182 | 0.7333 | 0.8333 |

## Cardinality Invariance

| group | same_count | more_less |
|---|---:|---:|
| direct_symbolic | 0.0000 | 0.0000 |
| direct_compute_matched | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.0000 | 0.0000 |
| concrete_sequential | 0.6750 | 0.4917 |
| interleaved_concrete_symbolic | 0.0000 | 0.0000 |
| paired_representation | 0.0750 | 0.0000 |

## Successor Results

| group | successor_symbolic | successor_concrete |
|---|---:|---:|
| direct_symbolic | 0.0000 | 0.0000 |
| direct_compute_matched | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.0000 | 0.0000 |
| concrete_sequential | 0.0000 | 0.0000 |
| interleaved_concrete_symbolic | 0.0000 | 0.0000 |
| paired_representation | 0.1000 | 0.0000 |

## Concrete Small Addition

| group | small_concrete_add |
|---|---:|
| direct_symbolic | 0.0000 |
| direct_compute_matched | 0.0000 |
| symbolic_concept_first | 0.0000 |
| concrete_sequential | 0.6250 |
| interleaved_concrete_symbolic | 0.5875 |
| paired_representation | 0.1375 |

## Symbolic Bridge Sample Efficiency

| run | small symbolic ADD |
|---|---:|
| not run yet | 0.0000 |

## Place Value

| group | place_value | place_value_holdout |
|---|---:|---:|
| direct_symbolic | 0.0000 | 0.0000 |
| direct_compute_matched | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.0000 | 0.0000 |
| concrete_sequential | 0.0000 | 0.0000 |
| interleaved_concrete_symbolic | 0.0000 | 0.0000 |
| paired_representation | 0.0000 | 0.0000 |

## Base-10 Grouping

| group | base10_grouping | base10_ungrouping |
|---|---:|---:|
| direct_symbolic | 0.0000 | 0.0000 |
| direct_compute_matched | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.0000 | 0.0000 |
| concrete_sequential | 0.0000 | 0.0000 |
| interleaved_concrete_symbolic | 0.0000 | 0.0000 |
| paired_representation | 0.0000 | 0.0000 |

## Multi-Digit Addition

| group | add_2digit_no_regroup | add_2digit_regroup |
|---|---:|---:|
| direct_symbolic | 0.9812 | 1.0000 |
| direct_compute_matched | 0.9563 | 0.9812 |
| symbolic_concept_first | 0.9938 | 0.8562 |
| concrete_sequential | 0.9125 | 0.8125 |
| interleaved_concrete_symbolic | 0.9500 | 0.8125 |
| paired_representation | 0.9938 | 0.9437 |

## Pure Symbolic Transfer

| group | pure_symbolic_clean_id | pure_symbolic_digit_pair_ood | pure_symbolic_range_ood | length_3 | length_4 | length_5 | length_6 | length_8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct_symbolic | 0.9958 | 0.0000 | 0.0125 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| direct_compute_matched | 0.9708 | 0.0000 | 0.0063 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.9500 | 0.0042 | 0.0063 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| concrete_sequential | 0.9250 | 0.0083 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| interleaved_concrete_symbolic | 0.9250 | 0.0167 | 0.0125 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| paired_representation | 0.9708 | 0.0000 | 0.0063 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Direct vs Rule vs Concept vs Concrete

| baseline | clean ID | digit-pair OOD | range OOD | length3 | length8 |
|---|---:|---:|---:|---:|---:|
| M-19.1 RFFT | 1.0000 trained lengths 1-5 | 0.0333 | n/a | 1.0000 trained | 0.0000 |
| M-19.1 Turing | 1.0000 trained lengths 1-5 | 0.0000 | n/a | 1.0000 trained | 0.0000 |
| direct_symbolic | 0.9958 | 0.0000 | 0.0125 | 0.0000 | 0.0000 |
| direct_compute_matched | 0.9708 | 0.0000 | 0.0063 | 0.0000 | 0.0000 |
| symbolic_concept_first | 0.9500 | 0.0042 | 0.0063 | 0.0000 | 0.0000 |
| concrete_sequential | 0.9250 | 0.0083 | 0.0000 | 0.0000 | 0.0000 |
| interleaved_concrete_symbolic | 0.9250 | 0.0167 | 0.0125 | 0.0000 | 0.0000 |
| paired_representation | 0.9708 | 0.0000 | 0.0063 | 0.0000 | 0.0000 |

## Compute-Matched Comparison

| group | pure_symbolic_clean_id | pure_symbolic_digit_pair_ood | length_3 |
|---|---:|---:|---:|
| direct_symbolic | 0.9958 | 0.0000 | 0.0000 |
| direct_compute_matched | 0.9708 | 0.0000 | 0.0000 |

## Representation Probes

| group | same quantity cosine | different quantity cosine | centroid probe acc |
|---|---:|---:|---:|
| direct_symbolic | 0.9934 | 0.9930 | 0.5682 |
| interleaved_concrete_symbolic | 0.9942 | 0.9939 | 0.6591 |

## Ablations

Skipped: no promising concrete/interleaved result yet.

## Few-Shot Subtraction Transfer

Not launched in M-19.2 unless addition/concept gates are promising. This milestone intentionally does not train full subtraction.

## Multi-Seed Confirmation

| group | seeds | digit-pair OOD mean | std |
|---|---:|---:|---:|
| not run yet | 0 | 0.0000 | 0.0000 |

## Interpretation

STOP: cardinality did not generalize to held-out object families. Do not interpret later addition as grounded numeracy yet.

## Recommended Next Step

Tighten object-token curriculum and COUNT formatting before any addition work.

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `0a231f4`

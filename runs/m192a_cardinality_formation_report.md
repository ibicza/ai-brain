# M-19.2a Cardinality Formation Laboratory

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## M-19.2 Failure Audit

M-19.2 failed the COUNT gate: saturated count-only reached seen 0.9091, held-out object 0.6667, and held-out format 0.1818. M-19.2a isolates cardinality formation before any addition work.

## Tokenization Audit

| object | max count | object span visible | aggregate leak rows |
|---|---:|---|---:|
| a | 20 | True | 0 |
| k | 20 | True | 0 |
| m | 20 | True | 0 |
| mixed | 5 | True | 0 |
| n | 20 | True | 0 |
| q | 20 | True | 0 |
| w | 20 | True | 0 |
| x | 20 | True | 0 |
| y | 20 | True | 0 |
| z | 20 | True | 0 |

## Evaluation Axis Definitions

| split | count | task types | object families | counts |
|---|---:|---|---|---|
| global_count_length_ood | 30 | {'m192a.count.global': 30} | ['a', 'k', 'x'] | [11, 12, 13, 14, 15, 16, 17, 18, 19, 20] |
| iterative_count_length_ood | 20 | {'m192a.count.iterative': 20} | ['a', 'x'] | [11, 12, 13, 14, 15, 16, 17, 18, 19, 20] |
| iterative_count_seen | 33 | {'m192a.count.iterative': 33} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| local_successor_heldout_object | 40 | {'m192a.successor.local': 40} | ['q', 'w', 'y', 'z'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] |
| local_successor_seen | 30 | {'m192a.successor.local': 30} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] |
| matching_heldout_object | 140 | {'m192a.matching.one_to_one': 140} | [] | [] |
| matching_length_ood | 120 | {'m192a.matching.one_to_one': 120} | [] | [] |
| matching_seen | 140 | {'m192a.matching.one_to_one': 140} | [] | [] |
| mixed_object_identity | 11 | {'m192a.count.global': 11} | ['mixed'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| more_less | 160 | {'m192a.compare.more_less': 160} | [] | [] |
| peano_length_ood | 10 | {'m192a.peano.depth': 10} | [] | [11, 12, 13, 14, 15, 16, 17, 18, 19, 20] |
| peano_seen | 11 | {'m192a.peano.depth': 11} | [] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| pointer_count_length_ood | 20 | {'m192a.count.pointer_tape': 20} | ['a', 'x'] | [11, 12, 13, 14, 15, 16, 17, 18, 19, 20] |
| pointer_count_seen | 33 | {'m192a.count.pointer_tape': 33} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| prompt_syntax_ood | 33 | {'m192a.count.global': 33} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| reordered_object_identity | 11 | {'m192a.invariance.reordered': 11} | [] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| seen_count_heldout_object | 44 | {'m192a.count.global': 44} | ['q', 'w', 'y', 'z'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| seen_count_seen_object | 33 | {'m192a.count.global': 33} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| separator_ood | 66 | {'m192a.count.global': 66} | ['a', 'k', 'x'] | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| successor_11_20 | 30 | {'m192a.successor.local': 30} | ['a', 'k', 'x'] | [10, 11, 12, 13, 14, 15, 16, 17, 18, 19] |

Prompt intersection max: `0`.
Strict full-count 11..20 in train: `{'global_count': 0, 'hybrid_scaffolded': 0, 'hybrid_strict': 0, 'iterative_count': 0, 'local_successor_scaffolded': 0, 'local_successor_strict': 0, 'matching': 0, 'pointer_tape': 0}`.

## Global Count

| method | seen_count_seen_object | seen_count_heldout_object | mixed_object_identity | reordered_object_identity | separator_ood | global_count_length_ood | more_less |
|---|---:|---:|---:|---:|---:|---:|---:|
| global_count | 0.1818 | 0.1818 | 0.1818 | 0.0000 | 0.1818 | 0.0000 | 0.0000 |

## Local Successor

| method | local_successor_seen | local_successor_heldout_object | successor_11_20 |
|---|---:|---:|---:|
| local_successor_strict | 0.0000 | 0.0000 | 0.0000 |
| local_successor_scaffolded | 0.0000 | 0.0000 | 0.0000 |

## Iterative Counting

| method | seen_count_seen_object | seen_count_heldout_object | mixed_object_identity | reordered_object_identity | separator_ood | global_count_length_ood | more_less |
|---|---:|---:|---:|---:|---:|---:|---:|
| iterative_count | 0.0000 | 0.0909 | 0.0909 | 0.0000 | 0.1212 | 0.0000 | 0.0000 |

| method | split | state_count_exact | remaining_exact | step_transition_valid | pair_count_exact | remain_exact |
|---|---|---:|---:|---:|---:|---:|
| iterative_count | iterative_count_length_ood | 0.0000 | 0.0000 | 0.4000 | 0.0000 | 0.0000 |

## Pointer/Tape Counting

| method | seen_count_seen_object | seen_count_heldout_object | mixed_object_identity | reordered_object_identity | separator_ood | global_count_length_ood | more_less |
|---|---:|---:|---:|---:|---:|---:|---:|
| pointer_tape | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

| method | split | state_count_exact | remaining_exact | step_transition_valid | pair_count_exact | remain_exact |
|---|---|---:|---:|---:|---:|---:|
| pointer_tape | pointer_count_length_ood | 0.0000 | 0.0000 | 0.2000 | 0.0000 | 0.0000 |

## Peano/Successor Control

| method | peano_seen | peano_length_ood | successor_11_20 |
|---|---:|---:|---:|
| local_successor_strict | 0.0909 | 0.0000 | 0.0000 |
| local_successor_scaffolded | 0.0000 | 0.3000 | 0.0000 |
| hybrid_scaffolded | 0.3636 | 0.7000 | 0.0000 |

## One-to-One Matching

| method | matching_seen | matching_heldout_object | matching_length_ood |
|---|---:|---:|---:|
| matching | 0.4286 | 0.3714 | 0.3750 |

| method | split | state_count_exact | remaining_exact | step_transition_valid | pair_count_exact | remain_exact |
|---|---|---:|---:|---:|---:|---:|
| matching | matching_length_ood | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.3750 |

## Hybrid Curriculum

| method | seen_count_seen_object | seen_count_heldout_object | mixed_object_identity | reordered_object_identity | separator_ood | global_count_length_ood | more_less |
|---|---:|---:|---:|---:|---:|---:|---:|
| hybrid_strict | 0.0303 | 0.0909 | 0.0000 | 0.0000 | 0.0606 | 0.0000 | 0.7625 |
| hybrid_scaffolded | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0303 | 0.0000 | 0.7188 |

## Object Identity Invariance

| method | seen_count_heldout_object | mixed_object_identity | reordered_object_identity |
|---|---:|---:|---:|
| global_count | 0.1818 | 0.1818 | 0.0000 |
| local_successor_strict | 0.0000 | 0.0000 | 0.0000 |
| local_successor_scaffolded | 0.0000 | 0.0000 | 0.0000 |
| iterative_count | 0.0909 | 0.0909 | 0.0000 |
| pointer_tape | 0.0000 | 0.0000 | 0.0000 |
| matching | 0.0000 | 0.0000 | 0.0000 |
| hybrid_strict | 0.0909 | 0.0000 | 0.0000 |
| hybrid_scaffolded | 0.0000 | 0.0000 | 0.0000 |

## Length OOD 11..20

| method | iterative_count_length_ood | global_count_length_ood | matching_length_ood |
|---|---:|---:|---:|
| global_count | 0.0000 | 0.0000 | 0.0000 |
| local_successor_strict | 0.0000 | 0.0000 | 0.0000 |
| local_successor_scaffolded | 0.0000 | 0.0000 | 0.0000 |
| iterative_count | 0.0000 | 0.0000 | 0.0000 |
| pointer_tape | 0.0000 | 0.0000 | 0.0000 |
| matching | 0.0000 | 0.0000 | 0.3750 |
| hybrid_strict | 0.0000 | 0.0000 | 0.3333 |
| hybrid_scaffolded | 0.0000 | 0.0000 | 0.1833 |

## Format Decomposition

| method | separator_ood | prompt_syntax_ood |
|---|---:|---:|
| global_count | 0.1818 | 0.0606 |
| local_successor_strict | 0.0000 | 0.0000 |
| local_successor_scaffolded | 0.0000 | 0.0000 |
| iterative_count | 0.1212 | 0.0909 |
| pointer_tape | 0.0000 | 0.0000 |
| matching | 0.0000 | 0.0000 |
| hybrid_strict | 0.0606 | 0.1212 |
| hybrid_scaffolded | 0.0303 | 0.0303 |

## Representation Probes

| method | same cosine | different cosine | centroid acc | successor direction cosine |
|---|---:|---:|---:|---:|
| global_count | 0.9912 | 0.9917 | 0.8182 | -0.0776 |

## Sample Efficiency

| method | split | >=.80 | >=.90 | >=.95 | >=.98 |
|---|---|---:|---:|---:|---:|
| global_count | global_count_length_ood | not reached | not reached | not reached | not reached |
| global_count | seen_count_heldout_object | not reached | not reached | not reached | not reached |
| global_count | seen_count_seen_object | not reached | not reached | not reached | not reached |
| hybrid_scaffolded | global_count_length_ood | not reached | not reached | not reached | not reached |
| hybrid_scaffolded | seen_count_heldout_object | not reached | not reached | not reached | not reached |
| hybrid_scaffolded | seen_count_seen_object | not reached | not reached | not reached | not reached |
| hybrid_strict | global_count_length_ood | not reached | not reached | not reached | not reached |
| hybrid_strict | seen_count_heldout_object | not reached | not reached | not reached | not reached |
| hybrid_strict | seen_count_seen_object | not reached | not reached | not reached | not reached |
| iterative_count | global_count_length_ood | not reached | not reached | not reached | not reached |
| iterative_count | seen_count_heldout_object | not reached | not reached | not reached | not reached |
| pointer_tape | global_count_length_ood | not reached | not reached | not reached | not reached |
| pointer_tape | seen_count_heldout_object | not reached | not reached | not reached | not reached |

## Capacity Check if gated

skipped: no method passed the seen/object/mixed/separator invariance gate.

## Recurrent Control if gated

skipped: Transformer methods did not pass the gating criteria.

## Interpretation

OUTCOME F: none of the tested textual counting-stick procedures formed robust cardinality under the current decoder-only Transformer setup.

## Recommended Next Step

Stop textual counting-stick grounding for this decoder setup unless a more structural input representation is introduced.

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `7713f44`

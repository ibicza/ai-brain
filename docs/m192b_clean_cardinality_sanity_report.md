# M-19.2b Clean Cardinality Sanity Report

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## Nuisance Audit

| source | field | present in prompt? | semantic necessity | action |
|---|---|---|---|---|
| M-19.2 generator | CASE/example IDs | False | none | audited; no clean-count prompt fix required |
| M-19.2 generator | train/eval or seed labels | False | metadata/report only | audited; no clean-count prompt fix required |
| M-19.2a pre-fix generator | CASE/example IDs | True | none | removed from generator prompts in this patch |
| M-19.2a pre-fix generator | train/eval labels | True | metadata/report only | removed TRAIN_ONLY prompt-disjoint marker in this patch |
| M-19.2b generated datasets | forbidden prompt markers | False | none | test-enforced absent |

## Successor Fit

| run | successor_symbol_train_fit | successor_symbol_eval_same |
|---|---:|---:|
| successor_symbol | 1.0000 | 1.0000 |

## Object-Independent Successor

| run | local_successor_train_fit | local_successor_seen_object | local_successor_heldout_object | local_successor_mixed_object |
|---|---:|---:|---:|---:|
| local_successor | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Clean COUNT

| run | global_count_train_fit | global_count_seen_object | global_count_heldout_object | global_count_mixed_object |
|---|---:|---:|---:|---:|
| global_count | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Clean SAME_COUNT

| run | same_count_train_fit | same_count_seen_object | same_count_heldout_object | same_count_mixed_object |
|---|---:|---:|---:|---:|
| same_count | 1.0000 | 1.0000 | 1.0000 | 0.5909 |

## M-19.2 vs M-19.2a vs M-19.2b

| experiment | count seen | heldout object | mixed/format | length OOD | note |
|---|---:|---:|---:|---:|---|
| M-19.2 diagnostic_count_only | 0.9091 | 0.6667 | 0.1818 | n/a | pre-M-19.2b baseline |
| M-19.2a global_count | 0.1818 | 0.1818 | 0.1818 | 0.0000 | CASE-confounded prompt surface |
| M-19.2b clean global_count | 1.0000 | 1.0000 | 1.0000 | 0.0000 | nuisance-free canonical prompt |

## Isolated OOD Axes

| run | global_count_heldout_object | global_count_mixed_object | global_count_separator_ood | global_count_length_ood |
|---|---:|---:|---:|---:|
| global_count | 1.0000 | 1.0000 | 0.3091 | 0.0000 |

## Iterative Counting

| run | iterative_count_train_fit | iterative_count_seen | iterative_count_length_ood |
|---|---:|---:|---:|
| iterative_count | 1.0000 | 1.0000 | 0.0000 |

Trace diagnostics: `{"final_line_present": 1.0, "halt_exact": 1.0, "state_exact": 0.0, "transition_valid": 0.35}`

## Recurrent Control

| run | iterative_count_train_fit | iterative_count_seen | iterative_count_length_ood |
|---|---:|---:|---:|
| gru_iterative_count | 1.0000 | 1.0000 | 0.0000 |

## Semantic Overlap Audit

| pair | raw prompt intersection | interpretation |
|---|---:|---|
| global_count__global_count_heldout_object | 1 | intentional fit/memorization axis when syntax and semantics are identical |
| global_count__global_count_mixed_object | 2 | intentional fit/memorization axis when syntax and semantics are identical |
| global_count__global_count_seen_object | 51 | intentional fit/memorization axis when syntax and semantics are identical |
| global_count__global_count_separator_ood | 6 | intentional fit/memorization axis when syntax and semantics are identical |
| global_count__global_count_train_fit | 51 | intentional fit/memorization axis when syntax and semantics are identical |
| iterative_count__iterative_count_seen | 51 | intentional fit/memorization axis when syntax and semantics are identical |
| iterative_count__iterative_count_train_fit | 51 | intentional fit/memorization axis when syntax and semantics are identical |
| local_successor__local_successor_mixed_object | 50 | intentional fit/memorization axis when syntax and semantics are identical |
| local_successor__local_successor_seen_object | 50 | intentional fit/memorization axis when syntax and semantics are identical |
| local_successor__local_successor_train_fit | 50 | intentional fit/memorization axis when syntax and semantics are identical |
| same_count__same_count_heldout_object | 1 | intentional fit/memorization axis when syntax and semantics are identical |
| same_count__same_count_mixed_object | 1 | intentional fit/memorization axis when syntax and semantics are identical |
| same_count__same_count_seen_object | 178 | intentional fit/memorization axis when syntax and semantics are identical |
| same_count__same_count_train_fit | 178 | intentional fit/memorization axis when syntax and semantics are identical |
| successor_symbol__successor_symbol_eval_same | 10 | intentional fit/memorization axis when syntax and semantics are identical |
| successor_symbol__successor_symbol_train_fit | 10 | intentional fit/memorization axis when syntax and semantics are identical |

## Interpretation

F: clean COUNT and iterative seen fit, but both Transformer and GRU control fail length OOD.

## Checks

- remote/local ruff + pytest: passed
- commit hash at report build: `26105a1`

# M-19 Rule-Based Arithmetic Executor Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `91bc051`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## OOD Split Audit

| split | count | operand range | digit lengths | answer lengths | buckets | digit pairs |
|---|---:|---|---|---|---|---:|
| digit_combo_ood | 240 | 10..69 | {'2': 240} | {'1': 28, '2': 185, '3': 27} | {'borrow': 52, 'carry': 63, 'length_growth': 27, 'no_borrow': 68, 'no_carry': 30} | 78 |
| in_range | 240 | 10..69 | {'2': 240} | {'1': 30, '2': 188, '3': 22} | {'borrow': 53, 'carry': 50, 'length_growth': 22, 'no_borrow': 67, 'no_carry': 48} | 93 |
| length_3digit | 240 | 102..997 | {'3': 240} | {'1': 1, '2': 30, '3': 135, '4': 74} | {'borrow': 81, 'carry': 30, 'length_growth': 74, 'no_borrow': 39, 'no_carry': 16} | 100 |
| length_4digit | 240 | 1036..9991 | {'4': 240} | {'2': 2, '3': 20, '4': 148, '5': 70} | {'borrow': 100, 'carry': 38, 'length_growth': 70, 'no_borrow': 20, 'no_carry': 12} | 100 |
| length_5digit | 240 | 10067..99877 | {'5': 240} | {'2': 1, '3': 5, '4': 17, '5': 137, '6': 80} | {'borrow': 108, 'carry': 36, 'length_growth': 80, 'no_borrow': 12, 'no_carry': 4} | 100 |
| operand_range_ood | 240 | 70..99 | {'2': 240} | {'1': 66, '2': 54, '3': 120} | {'borrow': 40, 'length_growth': 120, 'no_borrow': 80} | 95 |
| result_range_ood | 240 | 10..99 | {'2': 240} | {'2': 120, '3': 120} | {'borrow': 44, 'length_growth': 120, 'no_borrow': 76} | 93 |
| train | 3000 | 10..69 | {'2': 3000} | {'1': 475, '2': 2192, '3': 333} | {'borrow': 540, 'carry': 431, 'length_growth': 333, 'no_borrow': 960, 'no_carry': 736} | 88 |

## Answer-Only Baseline

| eval axis | final NEM | trace exact | digit exact | carry/borrow |
|---|---:|---:|---:|---:|
| in_range | 0.3792 | 0.3792 | 0.3792 | 1.0000 |
| operand_range_ood | 0.1208 | 0.1208 | 0.1208 | 1.0000 |
| digit_combo_ood | 0.0792 | 0.0792 | 0.0792 | 1.0000 |
| result_range_ood | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| length_3digit | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| length_4digit | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| length_5digit | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| workspace_abi_heldout | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

## Scratchpad Baseline

| eval axis | final NEM | trace exact | digit exact | carry/borrow |
|---|---:|---:|---:|---:|
| in_range | 0.3833 | 0.3833 | 0.3833 | 0.9458 |
| operand_range_ood | 0.1917 | 0.0583 | 0.1917 | 0.7833 |
| digit_combo_ood | 0.0000 | 0.0000 | 0.0000 | 0.9458 |
| result_range_ood | 0.0042 | 0.0000 | 0.0042 | 0.8292 |
| length_3digit | 0.0000 | 0.0000 | 0.0000 | 0.0250 |
| length_4digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| length_5digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| workspace_abi_heldout | 0.0333 | 0.0000 | 0.0083 | 0.0042 |

## RFFT

| eval axis | final NEM | trace exact | digit exact | carry/borrow |
|---|---:|---:|---:|---:|
| in_range | 0.3833 | 0.3833 | 0.3833 | 0.9333 |
| operand_range_ood | 0.2083 | 0.0292 | 0.2083 | 0.8625 |
| digit_combo_ood | 0.0000 | 0.0000 | 0.0000 | 0.9292 |
| result_range_ood | 0.0000 | 0.0000 | 0.0000 | 0.9125 |
| length_3digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| length_4digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| length_5digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| workspace_abi_heldout | 0.0083 | 0.0000 | 0.0042 | 0.0000 |

## State-Machine Trace

| eval axis | final NEM | trace exact | digit exact | carry/borrow |
|---|---:|---:|---:|---:|
| in_range | 0.4208 | 0.4208 | 0.4208 | 0.9667 |
| operand_range_ood | 0.1875 | 0.0000 | 0.1875 | 0.7583 |
| digit_combo_ood | 0.0792 | 0.0792 | 0.0792 | 0.8500 |
| result_range_ood | 0.0000 | 0.0000 | 0.0000 | 0.9042 |
| length_3digit | 0.0000 | 0.0000 | 0.0000 | 0.0042 |
| length_4digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| length_5digit | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| workspace_abi_heldout | 0.0167 | 0.0000 | 0.0167 | 0.0458 |

## Length Curriculum

| variant | 3-digit | 4-digit | 5-digit |
|---|---:|---:|---:|
| answer | 0.0000 | 0.0000 | 0.0000 |
| scratchpad | 0.0000 | 0.0000 | 0.0000 |
| rfft | 0.0000 | 0.0000 | 0.0000 |
| state_machine | 0.0000 | 0.0000 | 0.0000 |

## Optional Self-Improvement

skipped: `state_machine` should be used for the next verified easy-to-hard run

## Workspace ABI Compatibility

| variant | operand OOD standalone | workspace ABI | gap |
|---|---:|---:|---:|
| answer | 0.1208 | 0.0000 | 0.1208 |
| scratchpad | 0.1917 | 0.0333 | 0.1583 |
| rfft | 0.2083 | 0.0083 | 0.2000 |
| state_machine | 0.1875 | 0.0167 | 0.1708 |

## Retrieved Operands -> Executor

skipped: workspace ABI executor did not pass OOD gate

## Multi-Seed

skipped: no variant passed gates, so multi-seed confirmation is premature

## Recommendation For Stage-1 Reasoning Executor

OUTCOME E: no tested representation reached operand-range OOD >= .95. Best exploratory variant was `state_machine`; current 5.29M objective/format still does not yield systematic arithmetic. Next run a controlled capacity/objective sweep.
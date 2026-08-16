# M-18 Segmented Context Workspace Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `d3ce290`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Dataset Verification

| item | value |
|---|---:|
| train mixed count | 3456 |
| clean eval count | 120 |
| prompt intersections | {'train_mixed_vs_clean': 0} |
| segment schema | m18.v1 |

## Flat vs Old Oracle vs Query-Isolated vs Workspace

| family | length | flat | old oracle | query-isolated | workspace |
|---|---:|---:|---:|---:|---:|
| neutral | 1 | 0.8917 | 0.7417 | 0.7417 | 0.7417 |
| neutral | 2 | 0.3333 | 0.7833 | 0.7833 | 0.7833 |
| neutral | 4 | 0.3000 | 0.8333 | 0.8333 | 0.8333 |
| neutral | 8 | 0.0583 | 0.9500 | 0.9500 | 0.9500 |
| neutral | 16 | 0.0000 | 0.7667 | 0.7667 | 0.7667 |
| neutral | 32 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| random_vocab | 1 | 0.4417 | 0.6667 | 0.6667 | 0.6667 |
| random_vocab | 2 | 0.0167 | 0.8250 | 0.8250 | 0.8250 |
| random_vocab | 4 | 0.0000 | 0.8167 | 0.8167 | 0.8167 |
| random_vocab | 8 | 0.0000 | 0.9583 | 0.9583 | 0.9583 |
| random_vocab | 16 | 0.0000 | 0.8500 | 0.8500 | 0.8500 |
| random_vocab | 32 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| natural_phrase | 1 | 0.5917 | 0.6667 | 0.6667 | 0.6667 |
| natural_phrase | 2 | 0.4167 | 0.8250 | 0.8250 | 0.8250 |
| natural_phrase | 4 | 0.0333 | 0.8417 | 0.8417 | 0.8417 |
| natural_phrase | 8 | 0.0000 | 0.9083 | 0.9083 | 0.9083 |
| natural_phrase | 16 | 0.0000 | 0.8917 | 0.8917 | 0.8917 |
| natural_phrase | 32 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| previous_arithmetic | 1 | 0.1250 | 0.9333 | 0.9333 | 0.9333 |
| previous_arithmetic | 2 | 0.0000 | 0.8000 | 0.8000 | 0.8000 |
| previous_arithmetic | 4 | 0.0000 | 0.8667 | 0.8667 | 0.8667 |
| previous_arithmetic | 8 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| previous_arithmetic | 16 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| hard_negative | 1 | 0.1167 | 0.8333 | 0.8333 | 0.8333 |
| hard_negative | 2 | 0.0000 | 0.8667 | 0.8667 | 0.8667 |
| hard_negative | 4 | 0.0000 | 0.8833 | 0.8833 | 0.8833 |
| hard_negative | 8 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |
| hard_negative | 16 | 0.0000 | 0.0000 | 0.8083 | 0.8083 |

## Distractor Robustness by Family and Length

| mode | clean | min easy<=16 | natural<=16 | arithmetic<=8 | hard<=8 |
|---|---:|---:|---:|---:|---:|
| flat_causal | 0.9917 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| old_key_oracle | 0.9917 | 0.6667 | 0.6667 | 0.0000 | 0.0000 |
| query_isolated | 0.9917 | 0.6667 | 0.6667 | 0.8000 | 0.8083 |
| workspace | 0.9917 | 0.6667 | 0.6667 | 0.8000 | 0.8083 |

## Layerwise Clean-vs-Distracted Hidden Similarity

| mode | role | layer | cosine | count |
|---|---|---:|---:|---:|
| flat_causal | answer_start | 1 | 0.9130 | 80 |
| flat_causal | answer_start | 2 | 0.8948 | 80 |
| flat_causal | answer_start | 3 | 0.8985 | 80 |
| flat_causal | answer_start | 4 | 0.9428 | 80 |
| flat_causal | op | 1 | 0.6552 | 80 |
| flat_causal | op | 2 | 0.8248 | 80 |
| flat_causal | op | 3 | 0.9146 | 80 |
| flat_causal | op | 4 | 0.9607 | 80 |
| flat_causal | operand_a | 1 | 0.5524 | 80 |
| flat_causal | operand_a | 2 | 0.7574 | 80 |
| flat_causal | operand_a | 3 | 0.8878 | 80 |
| flat_causal | operand_a | 4 | 0.9501 | 80 |
| flat_causal | operand_b | 1 | 0.9175 | 80 |
| flat_causal | operand_b | 2 | 0.8215 | 80 |
| flat_causal | operand_b | 3 | 0.9215 | 80 |
| flat_causal | operand_b | 4 | 0.9649 | 80 |
| query_isolated | answer_start | 1 | 0.9817 | 80 |
| query_isolated | answer_start | 2 | 0.9857 | 80 |
| query_isolated | answer_start | 3 | 0.9895 | 80 |
| query_isolated | answer_start | 4 | 0.9944 | 80 |
| query_isolated | op | 1 | 0.9135 | 80 |
| query_isolated | op | 2 | 0.9664 | 80 |
| query_isolated | op | 3 | 0.9873 | 80 |
| query_isolated | op | 4 | 0.9945 | 80 |
| query_isolated | operand_a | 1 | 0.9161 | 80 |
| query_isolated | operand_a | 2 | 0.9835 | 80 |
| query_isolated | operand_a | 3 | 0.9948 | 80 |
| query_isolated | operand_a | 4 | 0.9979 | 80 |
| query_isolated | operand_b | 1 | 0.9900 | 80 |
| query_isolated | operand_b | 2 | 0.9674 | 80 |
| query_isolated | operand_b | 3 | 0.9876 | 80 |
| query_isolated | operand_b | 4 | 0.9946 | 80 |
| workspace | answer_start | 1 | 0.9817 | 80 |
| workspace | answer_start | 2 | 0.9857 | 80 |
| workspace | answer_start | 3 | 0.9895 | 80 |
| workspace | answer_start | 4 | 0.9944 | 80 |
| workspace | op | 1 | 0.9135 | 80 |
| workspace | op | 2 | 0.9664 | 80 |
| workspace | op | 3 | 0.9873 | 80 |
| workspace | op | 4 | 0.9945 | 80 |
| workspace | operand_a | 1 | 0.9161 | 80 |
| workspace | operand_a | 2 | 0.9835 | 80 |
| workspace | operand_a | 3 | 0.9948 | 80 |
| workspace | operand_a | 4 | 0.9979 | 80 |
| workspace | operand_b | 1 | 0.9900 | 80 |
| workspace | operand_b | 2 | 0.9674 | 80 |
| workspace | operand_b | 3 | 0.9876 | 80 |
| workspace | operand_b | 4 | 0.9946 | 80 |

## Clean Accuracy

| source | mode | clean final NEM |
|---|---|---:|
| phase3 | flat_causal | 0.9917 |
| phase3 | old_key_oracle | 0.9917 |
| phase3 | query_isolated | 0.9917 |
| phase3 | workspace | 0.9917 |

## Relevant-Context Retrieval

skipped: oracle/training gate did not pass

## Oracle vs Learned Chunk Selection

skipped: oracle segment routing did not pass, so learned chunk selection was not run

## Variable-Binding Result

skipped: relevant-context gate did not pass

## ADD_SUB Composition

skipped: relevant-context gate did not pass

## Recommended Context Architecture

OUTCOME D: complete query/workspace isolation did not restore the required distractor robustness. Stop before learned routing and investigate representation/generation rather than adding another selector.
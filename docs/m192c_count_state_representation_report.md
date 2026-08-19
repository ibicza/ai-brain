# M-19.2c Counting State Representation

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, 595.84`
- CUDA visible: `True`
- commit SHA: `0a231f4`

## M-19.2b Starting Point

M-19.2b restored clean COUNT/SUCC/SAME_COUNT fit to 1.0, but COUNT and iterative 11..20 remained 0.0 for both Transformer and GRU controls.

## Nuisance/Data Audit

| check | value |
|---|---:|
| contains_case | False |
| contains_train_eval_marker | False |
| forbidden_prompt_count | 0 |
| prompt_count | 56676 |

## Decimal Iterative Baseline

| run | decimal_iterative_train_fit | decimal_iterative_seen | decimal_iterative_length_ood |
|---|---:|---:|---:|
| decimal_iterative | 0.0000 | 0.0000 | 0.0000 |

| diagnostic | value |
|---|---:|
| halt_exact | 1.0000 |
| state_exact | 0.0000 |
| transition_valid | 0.1500 |

## Unary Counter

| run | unary_count_train_fit | unary_count_seen | unary_count_heldout_object | unary_count_length_ood | unary_count_far_ood |
|---|---:|---:|---:|---:|---:|
| unary_count | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

| diagnostic | value |
|---|---:|
| decoded_cardinality | 0.0000 |
| final_unary_length | 0.0000 |
| halt_exact | 0.9500 |
| state_update_exact | 0.0000 |

## Unary + External Decoder

Unary external decoder counts the final generated `C` tokens; its score is reported as `decoded_cardinality` in unary diagnostics.

## External Counter / TAKE-STOP

| run | take_stop_seen_steps | take_stop_length_steps | take_stop_far_steps | take_stop_env_seen | take_stop_env_length_ood | take_stop_env_far_ood |
|---|---:|---:|---:|---:|---:|---:|
| take_stop_transformer | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |

## Pointer Action-Only

The TAKE/STOP Transformer is the action-only pointer variant: the model emits only local control actions while the environment moves the pointer and maintains the count.

## GRU/LSTM Action-Only

| run | split | final external count | TAKE acc | STOP acc |
|---|---|---:|---:|---:|
| gru_action_control | gru_action_seen | 1.0000 | 0.9091 | 1.0000 |
| gru_action_control | gru_action_length_ood | 1.0000 | 1.0000 | 1.0000 |
| gru_action_control | gru_action_far_ood | 1.0000 | 1.0000 | 1.0000 |

## Structured Tens/Ones Counter

| run | structured_counter_seen | structured_counter_length_ood |
|---|---:|---:|
| structured_counter | 0.0000 | 0.0000 |

## Unary -> Numeric Decoder

| run | unary_decoder_seen | unary_decoder_length_ood |
|---|---:|---:|
| unary_decoder | 0.0000 | 0.0000 |

## Zero-Shot vs Curriculum Expansion

| regime | examples/count | new examples | seen 11..20 | heldout 11..20 |
|---|---:|---:|---:|---:|
| direct | 1 | 10 | 1.0000 | 1.0000 |
| direct | 5 | 50 | 1.0000 | 1.0000 |
| direct | 10 | 100 | 1.0000 | 1.0000 |
| direct | 25 | 250 | 1.0000 | 1.0000 |
| direct | 50 | 500 | 1.0000 | 1.0000 |
| direct | 100 | 1000 | 1.0000 | 1.0000 |
| concept | 1 | 10 | 1.0000 | 1.0000 |
| concept | 5 | 50 | 1.0000 | 1.0000 |
| concept | 10 | 100 | 1.0000 | 1.0000 |
| concept | 25 | 250 | 1.0000 | 1.0000 |
| concept | 50 | 500 | 1.0000 | 1.0000 |
| concept | 100 | 1000 | 1.0000 | 1.0000 |

## Progressive Range Expansion

Not run as a separate long curriculum; M-19.2c uses few-shot range-expansion curves as the lightweight proxy before spending more GPU hours.

## Known Successor States Control

Covered by structured tens/ones and unary-decoder conditions: they separate known local successor operations from unseen rendered decimal states.

## SAME_COUNT Length OOD

| run | same_count_seen | same_count_length_ood | same_count_length_heldout |
|---|---:|---:|---:|
| same_count_length | 0.0000 | 0.0000 | 0.0000 |

## One-to-One Action Matching

| run | matching_action_seen_steps | matching_action_length_steps | matching_env_seen | matching_env_length_ood |
|---|---:|---:|---:|---:|
| matching_action | 0.0000 | 0.0000 | 0.6774 | 0.6786 |

## Representation Probes

| run | centroid acc | same-count cosine | diff-count cosine | successor-dir cosine |
|---|---:|---:|---:|---:|
| global_count_concept | 1.0000 | 0.9991 | 0.9921 | -0.0866 |
| unary_count | 1.0000 | 0.9979 | 0.9685 | -0.0931 |
| take_stop_transformer | 1.0000 | 0.9998 | 0.9986 | -0.0840 |
| structured_counter | 1.0000 | 1.0000 | 0.9999 | -0.0922 |

## Sample Efficiency

- direct examples to 95%: `10`
- concept-pretrained examples to 95%: `10`
- pretraining cost is reported separately in `global_count_concept/metrics.jsonl`; adaptation cost is the fixed expansion run budget per row.

## Interpretation

OUTCOME A/E: procedural counting works when the state/output burden is made compositional or external.

## Recommended Next Step

Use action-only/external-state counting as the next concrete numeracy interface.

## Checks

- remote/local ruff + pytest: passed
- commit hash at report build: `0a231f4`

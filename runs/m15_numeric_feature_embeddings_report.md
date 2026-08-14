# M-15 Numeric Feature Embeddings Report

## Checks

- Base commit before M-15: `79b18f9`
- Device: `cuda:0`, NVIDIA GeForce RTX 3050 Laptop GPU
- `uv run ruff format src tests`: passed, 52 files left unchanged
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: passed, 163 tests

## Implementation

M-15 adds optional numeric feature arrays to tokenized LM examples:

- `digit_value_ids`
- `digit_place_ids`
- `number_role_ids`
- `operation_step_ids`

Old text datasets and old tokenized cache payloads remain compatible: missing feature tensors are backfilled with `NONE = 0`.

The model side adds `numeric_debug` and `numeric_tiny` configs backed by `TinyNumericCausalTransformer`. The input embedding is:

```text
token + position + digit_value + digit_place + number_role + operation_step
```

Generation and eval now load numeric checkpoints and rebuild numeric feature tensors for the current generated context before each decoding step.

## Feature Extraction

Implemented extraction targets the compact digit trace family:

- Digit prompts: `ADD_DIGIT a=... b=... c=...`, `SUB_DIGIT a=... b=... borrow=...`
- Digit answers: `S ... C ...`, `S ... B ...`
- Composition prompts: `ADD2_COMPOSED ...`, `SUB2_COMPOSED ...`
- Compact trace rows: `A`, `B`, `U`, `T`, `OUT`

Feature extraction is partial-generation safe for short digit answers and trace rows, so eval does not require the full answer to already exist before assigning numeric features.

## Training Recipes

All runs used:

- config: `numeric_tiny`
- batch size: 8
- loss mode: `answer-only`
- tokenizer: `artifacts/tokenizers/stage1_bpe_8k.json`

| Recipe | Train data | Steps | Seq len | Checkpoint |
|---|---:|---:|---:|---|
| A digit table | `train_digit_table.jsonl` | 20000 | 128 | `runs/m15_a_digit_table_numeric_tiny_20k/checkpoints/step_020000.pt` |
| B 2digit composition | `train_2digit_composition.jsonl` | 8000 | 256 | `runs/m15_b_2digit_composition_numeric_tiny_8k/checkpoints/step_008000.pt` |
| C stage 2 | digit-table checkpoint -> `train_2digit_composition.jsonl` | 5000 | 256 | `runs/m15_c_stage2_from_digit20k_composition_numeric_tiny_5k/checkpoints/step_005000.pt` |
| C stage 3 | stage-2 checkpoint -> `train_mixed.jsonl` | 3000 | 256 | `runs/m15_c_stage3_mixed_replay_numeric_tiny_3k/checkpoints/step_003000.pt` |

Final training losses:

| Run | Train loss | Eval loss |
|---|---:|---:|
| A digit table 20k | 0.0255 | 0.2030 |
| B composition 8k | 0.0173 | 1.6661 |
| C stage 2 | 0.0009 | 1.7372 |
| C stage 3 | 0.0002 | 1.6698 |

Low train loss with poor composition eval indicates memorization/conditioning failure rather than lack of optimization steps.

## Results

Primary metric is `final_normalized_exact_match`.

| Recipe | Eval split | Full NEM | Final NEM | Empty rate | False answer rate | Avg tokens |
|---|---|---:|---:|---:|---:|---:|
| A digit table | digit seen | 0.6988 | 0.6988 | 0.0000 | 0.0000 | 7.01 |
| A digit table | digit holdout | 0.6800 | 0.6800 | 0.0000 | 0.0000 | 7.00 |
| B composition | 2digit same | 0.0000 | 0.0145 | 0.0000 | 0.0000 | 45.62 |
| B composition | 2digit holdout combo | 0.0000 | 0.0060 | 0.0000 | 0.0000 | 45.53 |
| B composition | 2digit far | 0.0000 | 0.0045 | 0.0000 | 0.0000 | 44.28 |
| C staged | digit seen | 0.6838 | 0.6838 | 0.0000 | 0.0000 | 7.01 |
| C staged | digit holdout | 0.7213 | 0.7213 | 0.0000 | 0.0000 | 7.01 |
| C staged | 2digit same | 0.0000 | 0.0225 | 0.0000 | 0.0000 | 31.02 |
| C staged | 2digit holdout combo | 0.0000 | 0.0025 | 0.0000 | 0.0000 | 32.84 |
| C staged | 2digit far | 0.0000 | 0.0025 | 0.0000 | 0.0000 | 46.33 |

M-14 comparison targets:

| Metric | M-14 old best | M-15 best |
|---|---:|---:|
| Digit-table holdout | 0.8100 | 0.7213 |
| 2digit holdout combo | 0.0645 | 0.0060 |
| 2digit far | 0.0175 | 0.0045 |

M-15 does not meet the useful thresholds:

- Digit-table holdout target: >= 0.90, observed 0.7213
- 2digit holdout-combo target: >= 0.15, observed 0.0060
- Far target: >= 0.05, observed 0.0045

## By Task Type

Recipe A digit-table holdout:

| Task type | Final NEM |
|---|---:|
| `arithmetic.digit_add_carry_out` | 0.7222 |
| `arithmetic.digit_add_no_carry` | 0.8182 |
| `arithmetic.digit_add_with_carry_input` | 0.7100 |
| `arithmetic.digit_sub_borrow_out` | 0.6667 |
| `arithmetic.digit_sub_no_borrow` | 0.6636 |
| `arithmetic.digit_sub_with_borrow_input` | 0.5700 |

Recipe C staged digit-table holdout:

| Task type | Final NEM |
|---|---:|
| `arithmetic.digit_add_carry_out` | 0.7556 |
| `arithmetic.digit_add_no_carry` | 0.8909 |
| `arithmetic.digit_add_with_carry_input` | 0.8050 |
| `arithmetic.digit_sub_borrow_out` | 0.6778 |
| `arithmetic.digit_sub_no_borrow` | 0.6455 |
| `arithmetic.digit_sub_with_borrow_input` | 0.5900 |

Recipe B composition:

| Split | Add final NEM | Sub final NEM |
|---|---:|---:|
| same | 0.0020 | 0.0265 |
| holdout combo | 0.0000 | 0.0124 |
| far | 0.0000 | 0.0090 |

Recipe C staged composition:

| Split | Add final NEM | Sub final NEM |
|---|---:|---:|
| same | 0.0234 | 0.0216 |
| holdout combo | 0.0010 | 0.0041 |
| far | 0.0000 | 0.0050 |

## Failure Samples

Digit holdout still makes basic table mistakes:

```text
Prompt: case 31003000004. SUB_DIGIT a=7 b=7 borrow=0
Expected: S 0 B 0
Predicted: S 9 B 1
```

```text
Prompt: case 31003000006. ADD_DIGIT a=8 b=7 c=1
Expected: S 6 C 1
Predicted: S 7 C 1
```

Composition often fails to preserve the compact trace grammar:

```text
Prompt: case 31008. ADD2_COMPOSED 84 + 65
Expected OUT: 149
Predicted OUT: 64
```

```text
Prompt: case 31006. SUB2_COMPOSED 47 - 14
Expected OUT: 33
Predicted OUT: 32
```

## Conclusion

Numeric embeddings are implemented and technically functional, but this first additive version does not improve the arithmetic bottleneck. It is worse than M-14 on digit-table holdout and much worse on 2digit composition.

The most likely issue is that randomly initialized additive feature embeddings perturb the token representation too strongly. The model can still overfit train data, but generation on compact traces becomes less stable and same-range composition collapses.

Decision: `no improvement`.

Recommended next step:

1. Keep the feature extraction infrastructure.
2. Replace raw additive numeric embeddings with zero-initialized or gated feature injection, so the model starts equivalent to the old tiny baseline and learns whether to use numeric features.
3. Evaluate the gated variant first on digit-table and 2digit composition only.
4. If gated embeddings still fail, move to input injection/recurrent reasoning rather than broad arithmetic or larger runs.

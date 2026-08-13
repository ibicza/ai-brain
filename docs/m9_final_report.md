# M-9 Recurrent Reasoning Baseline Report

## Implementation

Files changed/added:

- `src/ai_brain/model/config.py`
- `src/ai_brain/model/recurrent_transformer.py`
- `src/ai_brain/model/factory.py`
- `src/ai_brain/model/smoke.py`
- `src/ai_brain/training/loop.py`
- `src/ai_brain/eval/generation.py`
- `src/ai_brain/cli.py`
- `tests/test_recurrent_transformer.py`
- `tests/test_model_smoke.py`
- `tests/test_training.py`
- `tests/test_eval.py`

Architecture summary:

- `RecurrentCausalTransformer` uses token embedding, position embedding, dropout, input Transformer blocks, one shared recurrent Transformer block, output Transformer blocks, final norm, and tied LM head.
- `recurrent_debug`: d_model 64, heads 4, ffn 128, input_layers 1, recurrent_core 1 shared block, recurrent_cycles 2, output_layers 1.
- `recurrent_tiny`: d_model 128, heads 4, ffn 512, input_layers 1, recurrent_core 1 shared block, recurrent_cycles 4, output_layers 1.
- The recurrent core weights are shared: there is one `recurrent_core` module reused in a loop; tests verify parameter count does not change when only `recurrent_cycles` changes.
- Old M-8 tiny checkpoints remain loadable because missing `model_type` defaults to `tiny` during checkpoint loading.

Parameter counts:

| Config | Model | Parameters | Cycles | Shared recurrent core |
|---|---|---:|---:|---|
| `tiny` | `TinyCausalTransformer` | about 718K in 8k tokenizer training runs | n/a | n/a |
| `recurrent_debug` | `RecurrentCausalTransformer` | 133312 (133.31K) | 2 | yes |
| `recurrent_tiny` | `RecurrentCausalTransformer` | 758912 (758.91K) | 4 | yes |

## Checks

- `uv run ruff format src tests`: passed.
- `uv run ruff check src tests`: passed.
- `uv run pytest -q`: passed, 96 tests.
- `uv run ai-brain model-info --config recurrent_debug`: passed.
- `uv run ai-brain model-info --config recurrent_tiny`: passed.
- `uv run ai-brain model-smoke --config recurrent_debug`: passed on CUDA.
- `uv run ai-brain model-smoke --config recurrent_tiny`: passed on CUDA.

## Overfit Sanity

Run path: `runs/m9_overfit_recurrent_debug`.
Eval path: `runs/m9_overfit_recurrent_debug_eval`.

| Metric | Value |
|---|---:|
| Final train loss | 0.0001 |
| Final eval loss | 0.0000 |
| Exact match | 1.0000 |
| Normalized exact match | 1.0000 |

Conclusion: recurrent_debug overfit sanity passed. It reached normalized EM 1.0000 on the 128-example sanity dataset, so implementation/training/checkpoint/eval are functional.

## Focused Baseline Results

| Dataset | Old M-8.5 tiny EM | M-9 recurrent EM | Delta | False answer rate | Empty prediction rate |
|---|---:|---:|---:|---:|---:|
| `quantity_direct` | 0.3220 | 0.3220 | 0.0000 | 0.0000 | 0.1010 |
| `arithmetic` | 0.0075 | 0.0085 | 0.0010 | 0.0000 | 0.0610 |
| `state_change` | 0.2400 | 0.2467 | 0.0067 | 0.0000 | 0.0000 |
| `sorting_short` | 0.0110 | 0.0150 | 0.0040 | 0.0000 | 0.0630 |

Success-criteria summary:

- `quantity_direct`: no improvement, 0.3220 -> 0.3220, below useful >= 0.40.
- `arithmetic`: tiny improvement, 0.0075 -> 0.0085, below useful >= 0.02.
- `state_change`: tiny improvement, 0.2400 -> 0.2467, below useful >= 0.32.
- `sorting_short`: tiny improvement, 0.0110 -> 0.0150, below useful >= 0.03. Empty prediction rate improved from 0.0750 to 0.0630 and stays <= 0.20.

## By-Task Results

| Task type | Old EM | Recurrent EM | Delta |
|---|---:|---:|---:|
| `quantity.direct` | 0.1003 | 0.1003 | 0.0000 |
| `quantity.location_direct` | 0.1104 | 0.1104 | 0.0000 |
| `quantity.known_zero` | 0.7155 | 0.7155 | 0.0000 |
| `arithmetic.add` | 0.0000 | 0.0026 | 0.0026 |
| `arithmetic.subtract` | 0.0201 | 0.0175 | -0.0025 |
| `arithmetic.missing_addend` | 0.0051 | 0.0051 | 0.0000 |
| `state_change.add` | 0.0000 | 0.0000 | 0.0000 |
| `state_change.subtract` | 0.0252 | 0.0315 | 0.0063 |
| `sorting.ascending` | 0.0080 | 0.0101 | 0.0020 |
| `sorting.descending` | 0.0139 | 0.0199 | 0.0060 |

## Comparisons

### quantity_direct

Overall delta normalized EM: 0.0000.

### arithmetic

Overall delta normalized EM: 0.0010.

Most improved task types:

- `arithmetic.double_step`: 0.0117 -> 0.0163, delta 0.0047
- `arithmetic.add`: 0.0000 -> 0.0026, delta 0.0026

Most regressed task types:

- `arithmetic.subtract`: 0.0201 -> 0.0175, delta -0.0025

Still failed task types:

- `arithmetic.compare_sum`: 0.0000

### state_change

Overall delta normalized EM: 0.0067.

Most improved task types:

- `state_change.other_subject_no_change`: 0.1145 -> 0.1414, delta 0.0269
- `state_change.subtract`: 0.0252 -> 0.0315, delta 0.0063

Still failed task types:

- `state_change.add`: 0.0000

### sorting_short

Overall delta normalized EM: 0.0040.

Most improved task types:

- `sorting.descending`: 0.0139 -> 0.0199, delta 0.0060
- `sorting.ascending`: 0.0080 -> 0.0101, delta 0.0020

## Conclusion

Conclusion: **recurrent core does not solve transfer in this M-9 configuration**.

The implementation is functional and can overfit, but recurrent_tiny does not produce meaningful focused-dataset gains. It improves three datasets numerically, but the deltas are very small and do not reach useful thresholds. Quantity direct-copy is unchanged. Arithmetic and state-change numeric reasoning remain weak. Sorting empty-rate stays healthy and improves slightly, but exact match remains very low.

Recommended next step: **same-range vs shifted-range ablation**, followed by number representation/tokenizer work if the ablation confirms range transfer as the dominant failure. A second recurrent pass may still be useful later, but changing cycles alone is unlikely to fix the observed numeric transfer problem.

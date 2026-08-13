# M-10.1 Number Format + Scratchpad Pilot

Goal: test whether a tiny Transformer transfers arithmetic, copying, sorting, and state-change tasks better when only the dataset format changes.

The model architecture stays unchanged. The new data switch is:

```powershell
--answer-format normal_answer
--answer-format digit_spaced
--answer-format scratchpad
--answer-format reversed_answer
```

## Arithmetic Ablations

```powershell
uv run ai-brain generate-data-split `
  --output-dir datasets\m101\arithmetic_normal `
  --task-preset arithmetic `
  --train-count 20000 `
  --eval-count 2000 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format normal_answer

uv run ai-brain generate-data-split `
  --output-dir datasets\m101\arithmetic_digit_spaced `
  --task-preset arithmetic `
  --train-count 20000 `
  --eval-count 2000 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format digit_spaced

uv run ai-brain generate-data-split `
  --output-dir datasets\m101\arithmetic_scratchpad `
  --task-preset arithmetic `
  --train-count 20000 `
  --eval-count 2000 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format scratchpad

uv run ai-brain generate-data-split `
  --output-dir datasets\m101\arithmetic_reversed `
  --task-preset arithmetic `
  --train-count 20000 `
  --eval-count 2000 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format reversed_answer
```

## Sorting And State Change

```powershell
uv run ai-brain generate-data-split `
  --output-dir datasets\m101\sorting_scratchpad `
  --task-preset sorting_short `
  --train-count 10000 `
  --eval-count 1000 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format scratchpad

uv run ai-brain generate-data-split `
  --output-dir datasets\m101\state_change_scratchpad `
  --task-preset state_change `
  --train-count 15000 `
  --eval-count 1500 `
  --train-seed 1000 `
  --eval-seed 2000 `
  --answer-format scratchpad
```

Each split manifest records `answer_format`, and each formatted example stores `metadata.answer_format`. Non-normal formats also keep `metadata.original_prompt` and `metadata.original_answer`.

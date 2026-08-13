# M-8.4 Focused Curriculum Baselines

M-8.4 adds focused task presets for generating smaller curriculum slices that can be trained and evaluated before another broad Stage 1 run.

## Presets

- `quantity_direct`: `quantity.direct`, `quantity.location_direct`, `quantity.known_zero`
- `arithmetic`: `arithmetic.add`, `arithmetic.subtract`, `arithmetic.missing_addend`, `arithmetic.double_step`, `arithmetic.compare_sum`
- `state_change`: `state_change.add`, `state_change.subtract`, `state_change.other_subject_no_change`, `state_change.other_object_no_change`, `state_change.insufficient_start`
- `sorting_short`: `sorting.ascending`, `sorting.descending`

`--task-preset` is mutually exclusive with `--task-type`.

## Dataset Generation

```powershell
uv run ai-brain generate-data-split `
  --output-dir datasets\m84_quantity_direct `
  --train-count 10000 `
  --eval-count 1000 `
  --train-seed 3100 `
  --eval-seed 4100 `
  --task-preset quantity_direct

uv run ai-brain generate-data-split `
  --output-dir datasets\m84_arithmetic `
  --train-count 20000 `
  --eval-count 2000 `
  --train-seed 3200 `
  --eval-seed 4200 `
  --task-preset arithmetic

uv run ai-brain generate-data-split `
  --output-dir datasets\m84_state_change `
  --train-count 15000 `
  --eval-count 1500 `
  --train-seed 3300 `
  --eval-seed 4300 `
  --task-preset state_change

uv run ai-brain generate-data-split `
  --output-dir datasets\m84_sorting_short `
  --train-count 10000 `
  --eval-count 1000 `
  --train-seed 3400 `
  --eval-seed 4400 `
  --task-preset sorting_short `
  --train-profile train_short `
  --eval-profile eval_short
```

`sorting_short` defaults to `train_short`/`eval_short` when split profiles are not passed explicitly.

## Verification

```powershell
uv run ai-brain dataset-stats --input datasets\m84_quantity_direct\train.jsonl --task-type quantity.direct --task-type quantity.location_direct --task-type quantity.known_zero
uv run ai-brain dataset-stats --input datasets\m84_arithmetic\train.jsonl --task-type arithmetic.add --task-type arithmetic.subtract --task-type arithmetic.missing_addend --task-type arithmetic.double_step --task-type arithmetic.compare_sum
uv run ai-brain dataset-stats --input datasets\m84_state_change\train.jsonl --task-type state_change.add --task-type state_change.subtract --task-type state_change.other_subject_no_change --task-type state_change.other_object_no_change --task-type state_change.insufficient_start
uv run ai-brain dataset-stats --input datasets\m84_sorting_short\train.jsonl --task-type sorting.ascending --task-type sorting.descending
```

Each manifest includes `task_preset`, resolved `task_types`, split profiles, prompt dedup stats, and train/eval prompt intersection checks.

# M-12 Shifted-Prime Curriculum Validation Report

## Checks

- `uv run ruff format src tests`: passed (`51 files left unchanged`)
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: passed (`143 passed`)
- `uv run pytest tests\test_data_generation.py tests\test_cli.py -q`: passed (`79 passed`)
- `.\scripts\update-code-graph.ps1`: passed (`55 files, 496 nodes, 4311 edges`)
- Device used for training/eval: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`, 4GB)

## Scope

Implemented official `generate-range-primed` dataset generation and validated the shifted-prime curriculum recipes from the numeric-transfer research run. This did not launch 30k/50k training, did not change the model architecture, and did not implement embeddings.

## Implemented Feature

`uv run ai-brain generate-range-primed` writes:

- `train.jsonl`
- `train_same.jsonl`
- `train_shifted_prime.jsonl`
- `eval_same.jsonl`
- `eval_shifted_in_distribution.jsonl`
- `eval_shifted_holdout.jsonl`
- `eval_far_shifted.jsonl`
- `manifest.json`

Preset defaults are the M-12 recipes:

- `quantity_direct`: 10% shifted-prime + `place_role_numeric`
- `state_change`: 10% shifted-prime + `place_role_numeric`
- `sorting_short`: 20% shifted-prime + `normal_answer`
- `arithmetic`: 50% shifted-prime + `scratchpad`

## Dataset Verification


### quantity_direct

- recipe: 10% shifted-prime + place_role_numeric
- answer_format: `place_role_numeric`; shifted_prime_fraction: `0.1`
- counts: train_same=9000, train_shifted_prime=1000, eval_same=1000, eval_shifted_in_distribution=1000, eval_shifted_holdout=1000, eval_far_shifted=1000
- profiles: train_same:train_same, train_shifted_prime:train_shifted_prime, eval_same:eval_same, eval_shifted_in_distribution:eval_shifted_in_distribution, eval_shifted_holdout:eval_shifted_holdout, eval_far_shifted:eval_far_shifted
- seeds: train_same:12001, train_shifted_prime:12101, eval_same:12201, eval_shifted_in_distribution:12301, eval_shifted_holdout:12401, eval_far_shifted:12501
- prompt checks: all_prompt_intersections_zero=True; no_train_prime_eval_prompt_intersections=True; all_task_types_present=True
- numeric input ranges: train_same=1..30 (30 unique); train_shifted_prime=21..60 (39 unique); eval_same=1..30 (30 unique); eval_shifted_in_distribution=21..60 (40 unique); eval_shifted_holdout=61..100 (40 unique); eval_far_shifted=101..300 (194 unique)
- train_prime numeric overlap with eval splits: eval_same:set=9 / eval_frac=0.300, eval_shifted_in_distribution:set=39 / eval_frac=0.975, eval_shifted_holdout:set=0 / eval_frac=0.000, eval_far_shifted:set=0 / eval_frac=0.000
- train_prime by-key overlap counts: eval_same (count:9); eval_shifted_in_distribution (count:39); eval_shifted_holdout (count:0); eval_far_shifted (count:0)
- training: tiny, steps=5000, batch_size=8, sequence_length=256, loss_mode=answer-only, max_new_tokens=128

### state_change

- recipe: 10% shifted-prime + place_role_numeric
- answer_format: `place_role_numeric`; shifted_prime_fraction: `0.1`
- counts: train_same=13500, train_shifted_prime=1500, eval_same=1500, eval_shifted_in_distribution=1500, eval_shifted_holdout=1500, eval_far_shifted=1500
- profiles: train_same:train_same, train_shifted_prime:train_shifted_prime, eval_same:eval_same, eval_shifted_in_distribution:eval_shifted_in_distribution, eval_shifted_holdout:eval_shifted_holdout, eval_far_shifted:eval_far_shifted
- seeds: train_same:13001, train_shifted_prime:13101, eval_same:13201, eval_shifted_in_distribution:13301, eval_shifted_holdout:13401, eval_far_shifted:13501
- prompt checks: all_prompt_intersections_zero=True; no_train_prime_eval_prompt_intersections=True; all_task_types_present=True
- numeric input ranges: train_same=0..30 (31 unique); train_shifted_prime=1..60 (60 unique); eval_same=0..30 (31 unique); eval_shifted_in_distribution=1..60 (60 unique); eval_shifted_holdout=1..100 (98 unique); eval_far_shifted=1..300 (292 unique)
- train_prime numeric overlap with eval splits: eval_same:set=30 / eval_frac=0.968, eval_shifted_in_distribution:set=60 / eval_frac=1.000, eval_shifted_holdout:set=58 / eval_frac=0.592, eval_far_shifted:set=53 / eval_frac=0.182
- train_prime by-key overlap counts: eval_same (delta:28, start:11); eval_shifted_in_distribution (delta:52, start:41); eval_shifted_holdout (delta:54, start:10); eval_far_shifted (delta:49, start:0)
- training: tiny, steps=8000, batch_size=8, sequence_length=256, loss_mode=answer-only, max_new_tokens=128

### sorting_short

- recipe: 20% shifted-prime + normal_answer
- answer_format: `normal_answer`; shifted_prime_fraction: `0.2`
- counts: train_same=8000, train_shifted_prime=2000, eval_same=1000, eval_shifted_in_distribution=1000, eval_shifted_holdout=1000, eval_far_shifted=1000
- profiles: train_same:train_same, train_shifted_prime:train_shifted_prime, eval_same:eval_same, eval_shifted_in_distribution:eval_shifted_in_distribution, eval_shifted_holdout:eval_shifted_holdout, eval_far_shifted:eval_far_shifted
- seeds: train_same:14001, train_shifted_prime:14101, eval_same:14201, eval_shifted_in_distribution:14301, eval_shifted_holdout:14401, eval_far_shifted:14501
- prompt checks: all_prompt_intersections_zero=True; no_train_prime_eval_prompt_intersections=True; all_task_types_present=True
- numeric input ranges: train_same=0..49 (50 unique); train_shifted_prime=20..69 (50 unique); eval_same=0..49 (50 unique); eval_shifted_in_distribution=20..69 (50 unique); eval_shifted_holdout=70..119 (50 unique); eval_far_shifted=120..239 (120 unique)
- train_prime numeric overlap with eval splits: eval_same:set=30 / eval_frac=0.600, eval_shifted_in_distribution:set=50 / eval_frac=1.000, eval_shifted_holdout:set=0 / eval_frac=0.000, eval_far_shifted:set=0 / eval_frac=0.000
- train_prime by-key overlap counts: eval_same (numbers:30); eval_shifted_in_distribution (numbers:50); eval_shifted_holdout (numbers:0); eval_far_shifted (numbers:0)
- training: tiny, steps=8000, batch_size=8, sequence_length=256, loss_mode=answer-only, max_new_tokens=32

### arithmetic

- recipe: 50% shifted-prime + scratchpad
- answer_format: `scratchpad`; shifted_prime_fraction: `0.5`
- counts: train_same=10000, train_shifted_prime=10000, eval_same=2000, eval_shifted_in_distribution=2000, eval_shifted_holdout=2000, eval_far_shifted=2000
- profiles: train_same:train_same, train_shifted_prime:train_shifted_prime, eval_same:eval_same, eval_shifted_in_distribution:eval_shifted_in_distribution, eval_shifted_holdout:eval_shifted_holdout, eval_far_shifted:eval_far_shifted
- seeds: train_same:15001, train_shifted_prime:15101, eval_same:15201, eval_shifted_in_distribution:15301, eval_shifted_holdout:15401, eval_far_shifted:15501
- prompt checks: all_prompt_intersections_zero=True; no_train_prime_eval_prompt_intersections=True; all_task_types_present=True
- numeric input ranges: train_same=0..60 (61 unique); train_shifted_prime=0..100 (101 unique); eval_same=0..59 (60 unique); eval_shifted_in_distribution=0..98 (98 unique); eval_shifted_holdout=0..158 (159 unique); eval_far_shifted=0..472 (421 unique)
- train_prime numeric overlap with eval splits: eval_same:set=60 / eval_frac=1.000, eval_shifted_in_distribution:set=98 / eval_frac=1.000, eval_shifted_holdout:set=101 / eval_frac=0.635, eval_far_shifted:set=100 / eval_frac=0.238
- train_prime by-key overlap counts: eval_same (a:31, b:46, c:43, d:1, total:20); eval_shifted_in_distribution (a:41, b:56, c:76, d:21, total:55); eval_shifted_holdout (a:20, b:60, c:86, d:0, total:0); eval_far_shifted (a:0, b:59, c:76, d:0, total:0)
- training: tiny, steps=10000, batch_size=8, sequence_length=256, loss_mode=answer-only, max_new_tokens=128


## Results Summary

| preset | same final NEM | shifted-in final NEM | holdout final NEM | far final NEM | interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| quantity_direct | 1.0000 | 1.0000 | 0.5990 | 0.3000 | practical but far-range bounded |
| state_change | 0.6080 | 0.5747 | 0.3833 | 0.1260 | mixed partial transfer |
| sorting_short | 0.6440 | 0.3230 | 0.0000 | 0.0000 | range patching |
| arithmetic | 0.2165 | 0.2000 | 0.0045 | 0.0015 | rule/capacity failure |

## Full Metrics

| preset | split | recipe | full normalized EM | final NEM | false answer rate | empty rate | avg tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| quantity_direct | eval_same | 10% shifted-prime + place_role_numeric | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 42.9550 |
| quantity_direct | eval_shifted_in_distribution | 10% shifted-prime + place_role_numeric | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 43.8130 |
| quantity_direct | eval_shifted_holdout | 10% shifted-prime + place_role_numeric | 0.5560 | 0.5990 | 0.0000 | 0.0000 | 44.4080 |
| quantity_direct | eval_far_shifted | 10% shifted-prime + place_role_numeric | 0.2940 | 0.3000 | 0.0000 | 0.0000 | 33.7090 |
| state_change | eval_same | 10% shifted-prime + place_role_numeric | 0.4007 | 0.6080 | 0.0000 | 0.0000 | 84.2153 |
| state_change | eval_shifted_in_distribution | 10% shifted-prime + place_role_numeric | 0.3680 | 0.5747 | 0.0000 | 0.0000 | 89.7400 |
| state_change | eval_shifted_holdout | 10% shifted-prime + place_role_numeric | 0.2853 | 0.3833 | 0.0000 | 0.0000 | 94.3367 |
| state_change | eval_far_shifted | 10% shifted-prime + place_role_numeric | 0.1260 | 0.1260 | 0.0000 | 0.0473 | 75.0067 |
| sorting_short | eval_same | 20% shifted-prime + normal_answer | 0.6440 | 0.6440 | 0.0000 | 0.0000 | 7.9860 |
| sorting_short | eval_shifted_in_distribution | 20% shifted-prime + normal_answer | 0.3230 | 0.3230 | 0.0000 | 0.0000 | 8.0270 |
| sorting_short | eval_shifted_holdout | 20% shifted-prime + normal_answer | 0.0000 | 0.0000 | 0.0000 | 0.0220 | 7.8080 |
| sorting_short | eval_far_shifted | 20% shifted-prime + normal_answer | 0.0000 | 0.0000 | 0.0000 | 0.1800 | 7.1100 |
| arithmetic | eval_same | 50% shifted-prime + scratchpad | 0.2045 | 0.2165 | 0.0000 | 0.0000 | 29.2760 |
| arithmetic | eval_shifted_in_distribution | 50% shifted-prime + scratchpad | 0.1945 | 0.2000 | 0.0000 | 0.0000 | 30.9775 |
| arithmetic | eval_shifted_holdout | 50% shifted-prime + scratchpad | 0.0000 | 0.0045 | 0.0000 | 0.0000 | 30.4820 |
| arithmetic | eval_far_shifted | 50% shifted-prime + scratchpad | 0.0000 | 0.0015 | 0.0000 | 0.0000 | 29.2090 |

## By-Task Final NEM


        ### quantity_direct / eval_same

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | quantity.direct | 351 | 1.0000 |
| quantity.known_zero | 340 | 1.0000 |
| quantity.location_direct | 309 | 1.0000 |

        ### quantity_direct / eval_shifted_in_distribution

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | quantity.direct | 314 | 1.0000 |
| quantity.known_zero | 385 | 1.0000 |
| quantity.location_direct | 301 | 1.0000 |

        ### quantity_direct / eval_shifted_holdout

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | quantity.direct | 332 | 0.3373 |
| quantity.known_zero | 355 | 1.0000 |
| quantity.location_direct | 313 | 0.4217 |

        ### quantity_direct / eval_far_shifted

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | quantity.direct | 361 | 0.0000 |
| quantity.known_zero | 324 | 0.9259 |
| quantity.location_direct | 315 | 0.0000 |

        ### state_change / eval_same

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | state_change.add | 319 | 0.0125 |
| state_change.insufficient_start | 263 | 1.0000 |
| state_change.other_object_no_change | 294 | 1.0000 |
| state_change.other_subject_no_change | 325 | 1.0000 |
| state_change.subtract | 299 | 0.0870 |

        ### state_change / eval_shifted_in_distribution

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | state_change.add | 314 | 0.0000 |
| state_change.insufficient_start | 258 | 1.0000 |
| state_change.other_object_no_change | 294 | 1.0000 |
| state_change.other_subject_no_change | 310 | 1.0000 |
| state_change.subtract | 324 | 0.0000 |

        ### state_change / eval_shifted_holdout

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | state_change.add | 302 | 0.0000 |
| state_change.insufficient_start | 301 | 1.0000 |
| state_change.other_object_no_change | 282 | 0.4504 |
| state_change.other_subject_no_change | 318 | 0.4623 |
| state_change.subtract | 297 | 0.0000 |

        ### state_change / eval_far_shifted

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | state_change.add | 330 | 0.0000 |
| state_change.insufficient_start | 260 | 0.7269 |
| state_change.other_object_no_change | 285 | 0.0000 |
| state_change.other_subject_no_change | 279 | 0.0000 |
| state_change.subtract | 346 | 0.0000 |

        ### sorting_short / eval_same

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | sorting.ascending | 481 | 0.6507 |
| sorting.descending | 519 | 0.6378 |

        ### sorting_short / eval_shifted_in_distribution

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | sorting.ascending | 504 | 0.3571 |
| sorting.descending | 496 | 0.2883 |

        ### sorting_short / eval_shifted_holdout

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | sorting.ascending | 467 | 0.0000 |
| sorting.descending | 533 | 0.0000 |

        ### sorting_short / eval_far_shifted

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | sorting.ascending | 504 | 0.0000 |
| sorting.descending | 496 | 0.0000 |

        ### arithmetic / eval_same

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | arithmetic.add | 414 | 0.5725 |
| arithmetic.compare_sum | 406 | 0.0665 |
| arithmetic.double_step | 398 | 0.0427 |
| arithmetic.missing_addend | 394 | 0.0660 |
| arithmetic.subtract | 388 | 0.3247 |

        ### arithmetic / eval_shifted_in_distribution

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | arithmetic.add | 393 | 0.6081 |
| arithmetic.compare_sum | 375 | 0.0453 |
| arithmetic.double_step | 368 | 0.0054 |
| arithmetic.missing_addend | 407 | 0.0319 |
| arithmetic.subtract | 457 | 0.2823 |

        ### arithmetic / eval_shifted_holdout

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | arithmetic.add | 395 | 0.0000 |
| arithmetic.compare_sum | 390 | 0.0000 |
| arithmetic.double_step | 405 | 0.0173 |
| arithmetic.missing_addend | 401 | 0.0000 |
| arithmetic.subtract | 409 | 0.0049 |

        ### arithmetic / eval_far_shifted

        | task_type | count | final NEM |
        | --- | ---: | ---: |
        | arithmetic.add | 392 | 0.0000 |
| arithmetic.compare_sum | 395 | 0.0000 |
| arithmetic.double_step | 434 | 0.0023 |
| arithmetic.missing_addend | 384 | 0.0000 |
| arithmetic.subtract | 395 | 0.0051 |


## Interpretation

- quantity_direct: same=1.0000, shifted_in_distribution=1.0000, holdout=0.5990, far=0.3000 -> practical curriculum fix, but still range-bounded at far shift.
- state_change: same=0.6080, shifted_in_distribution=0.5747, holdout=0.3833, far=0.1260 -> mixed: useful in-distribution gain with partial or task-specific holdout decay.
- sorting_short: same=0.6440, shifted_in_distribution=0.3230, holdout=0.0000, far=0.0000 -> range patching: learns the primed shifted band, not holdout/far transfer.
- arithmetic: same=0.2165, shifted_in_distribution=0.2000, holdout=0.0045, far=0.0015 -> rule/capacity failure, not solved by priming.

The key answer is: shifted-prime is mostly **range patching**, not broad numeric generalization. It is very effective inside the primed shifted band. Quantity and state keep some holdout signal, but far shifted exposes the boundary. Sorting and arithmetic collapse almost completely on holdout/far, despite useful in-distribution gains.

## Recommendation

Next step should not be more broad mixed training. Split arithmetic into primitives and evaluate separately:

- `arithmetic.add`
- `arithmetic.subtract`
- carry/no-carry
- borrow/no-borrow
- `missing_addend`
- `compare_sum`
- `double_step`

For quantity/state, shifted-prime can stay as a practical curriculum option, but it should be labelled range-bounded. For true transfer, the next architectural/data direction is digit/place/role embeddings or a compact digit-level tokenizer, then rerun this same M-12 suite.



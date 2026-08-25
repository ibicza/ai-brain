# M-25 Bilingual Query Dataset Report

## Frozen Dataset

Seed `25001` generated 32,000 prompt-disjoint rows:

| Split | Rows |
|---|---:|
| train | 20,000 |
| validation | 2,000 |
| calibration | 2,000 |
| development | 4,000 |
| blind final | 4,000 |

Language balance is 15,818 EN and 16,182 RU. Query balance is 22,081 supported, 3,645 hard-neighbor, 3,357 unsupported, and 2,917 ambiguous. All 89 skills and six semantic families occur in known rows; per-skill counts range from 230 to 333 over all splits.

The manifest persists full `language x kind`, `language x slice`, `family x language`, and `family x slice` contingency matrices. Language is sampled independently of skill instead of being coupled by row parity.

## Evaluation Slices

The data labels `ID`, `LEXICAL_HOLDOUT`, `TEMPLATE_HOLDOUT`, `VARIABLE_PERMUTATION`, `ORDER_HOLDOUT`, `CROSS_LANGUAGE`, `COMPOSED_OOD`, `UNKNOWN`, `AMBIGUOUS`, and `HARD_NEIGHBOR`. Register and order wording are preserved in the request, so counterfactual source/destination/order changes require a different target.

## Model Visibility

Only `text` and `language` are encoder inputs. Skill IDs, rule IDs, target hashes, split names, and evaluation slices are excluded from model-visible text. Generation validates this condition and rejects any text intersection across all splits.

## Blind Discipline

Blind requests and targets are physically separated:

- public hash: `61f01d95d3c3a9cfcd859981b6f26a973bb1ec12022e8115696a95df7dd7534b`
- hidden-target hash: `34bce9e034b0c1b4cecd1ef1972749e7236339a160b62e975c1c008c2cfc41f3`
- frozen before recipe selection: `2026-08-25T16:23:57.486070+00:00`

Training and threshold selection use train, validation, calibration, and development only. The selected recipe records both blind hashes and development-result hashes before hidden targets are joined for the single final evaluation.

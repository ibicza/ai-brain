# M-23 Controlled RU/EN Language-to-Spec

## Frozen Stage-1 Backend

- freeze: `stage1-acquisition-v1` / `11b573e`
- M-22.3a: conservative `OUTCOME B`; six black-box-validated families
- checks: `local 351 passed; karina 351 passed + 3 runtime-device tests; CUDA smoke passed`

## Remote Environment

- device: `NVIDIA GeForce RTX 5060 Laptop GPU` (`cuda:0`)
- credentials were not persisted

## Tokenizer Audit

- baseline RU tokens/sentence: 78.56
- bilingual RU tokens/sentence: 27.71
- baseline EN tokens/sentence: 124.67
- bilingual EN tokens/sentence: 28.90
- baseline / bilingual RU-to-EN token ratio: 0.630 / 0.959
- Cyrillic characters split into byte pieces: 669 / 0
- candidate register-reference token counts: {"en": {"A": 1, "A and B": 3, "from A into C": 4, "register A": 4}, "ru": {"A": 1, "A и B": 3, "из A в C": 5, "регистр A": 4}}
- retraining justified: `True`

## Supported Semantic Families

`NOOP`, `CLEAR`, `DRAIN`, `MERGE_TWO`, `MERGE_THREE`, `DROP_THEN_TRANSFER`.

## Dataset and Split Audit

- train / validation / test: 20000 / 2000 / 5000
- RU/EN train: {'en': 10000, 'ru': 10000}
- train statuses: {'AMBIGUOUS': 2000, 'CONTRADICTORY': 2000, 'SUPPORTED': 14000, 'UNSUPPORTED': 2000}
- train surface-template families: 12
- globally unique normalized text: `True`
- model-visible sample ID hits: `0`
- cross-language target pairs equal: `True`
- exact and normalized train/test text intersections: `0` for every split
- lexical holdout lexical-family intersection: `0`
- template holdout surface-family intersection: `0`
- variable-permutation specification intersection: `1` (the role-free `NOOP` specification)

## Deterministic Parser

| split | semantic exact | accepted precision | false accepted |
|---|---:|---:|---:|
| test_ambiguous | 1.0000 | 0.0000 | 0.0000 |
| test_contradictory | 1.0000 | 0.0000 | 0.0000 |
| test_cross_language | 0.9120 | 0.9325 | 0.0660 |
| test_id | 0.8760 | 0.9440 | 0.0520 |
| test_lexical_holdout | 0.9660 | 0.9660 | 0.0340 |
| test_negation_preserve | 0.3340 | 0.6208 | 0.2040 |
| test_order_holdout | 0.7100 | 0.9010 | 0.0780 |
| test_template_holdout | 0.4420 | 0.6406 | 0.2480 |
| test_unsupported | 1.0000 | 0.0000 | 0.0000 |
| test_variable_permutation | 0.9660 | 0.9660 | 0.0340 |
| validation | 0.9745 | 0.9636 | 0.0255 |

## Free JSON LM

Constrained control uses a schema-enumerated prefix grammar.

| split | whole exact | semantic exact | status accuracy | valid JSON | schema valid |
|---|---:|---:|---:|---:|---:|
| test_ambiguous | 0.9420 | 0.9420 | 0.9620 | 1.0000 | 1.0000 |
| test_contradictory | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| test_cross_language | 0.0620 | 0.0620 | 0.9920 | 1.0000 | 1.0000 |
| test_id | 0.3220 | 0.3220 | 0.9980 | 1.0000 | 1.0000 |
| test_lexical_holdout | 0.0280 | 0.0280 | 0.7440 | 1.0000 | 1.0000 |
| test_negation_preserve | 0.0120 | 0.0120 | 0.9720 | 1.0000 | 1.0000 |
| test_order_holdout | 0.0300 | 0.0300 | 0.8980 | 1.0000 | 1.0000 |
| test_template_holdout | 0.0440 | 0.0440 | 0.8800 | 1.0000 | 1.0000 |
| test_unsupported | 0.9980 | 0.9980 | 0.9980 | 1.0000 | 1.0000 |
| test_variable_permutation | 0.0400 | 0.0400 | 0.8140 | 1.0000 | 1.0000 |
| validation | 0.3205 | 0.3205 | 0.8525 | 1.0000 | 1.0000 |

## Typed Structured Parser

| split | semantic exact | accepted precision | false accepted |
|---|---:|---:|---:|
| test_ambiguous | 1.0000 | 0.0000 | 0.0000 |
| test_contradictory | 1.0000 | 0.0000 | 0.0000 |
| test_cross_language | 0.4260 | 0.6783 | 0.2020 |
| test_id | 0.8780 | 0.9184 | 0.0780 |
| test_lexical_holdout | 0.0000 | 0.0000 | 0.1840 |
| test_negation_preserve | 0.0000 | 0.0000 | 0.2180 |
| test_order_holdout | 0.2160 | 0.7606 | 0.0680 |
| test_template_holdout | 0.0100 | 0.0862 | 0.1060 |
| test_unsupported | 1.0000 | 0.0000 | 0.0000 |
| test_variable_permutation | 0.0000 | 0.0000 | 0.2480 |
| validation | 0.3000 | 0.0000 | 0.2005 |

## Field-Level Metrics

`{"allowed_primitives": 1.0, "drops": 1.0, "inputs": 0.9790794979079498, "outputs": 0.9309623430962343, "phase_constraints": 0.9184100418410042, "preserve": 0.9184100418410042, "terminate_when_empty": 0.9790794979079498, "transfers": 0.9184100418410042}`

## RU Results

ID semantic exact: `0.9080`.

## EN Results

ID semantic exact: `0.8480`. Absolute RU/EN
gap: `0.0600`.

## Cross-Language Consistency

- semantic specification equality: `0.0000`
- field-level equality: `0.0000`
- downstream execution equality: `0.0000`

## Lexical Holdout

Semantic exact: `0.0000`.

## Template Holdout

Semantic exact: `0.0100`.

## Variable Permutation

Semantic exact: `0.0000`.

## Negation / Preserve

Semantic exact: `0.0000`.

## Ambiguous Inputs

Status accuracy: `1.0000`.

## Contradictory Inputs

Status accuracy: `1.0000`.

## Unsupported Inputs

Status accuracy: `1.0000`.

## Clarification Loop

Question correctness: `1.0000`; one-round resolved
specification: `1.0000`.

## Confidence / Abstention

Coverage: `0.9560`; accepted precision:
`0.9184`; incorrect confidently accepted:
`0.0780`. Threshold is calibrated on
validation only; test labels do not alter it.

Validation risk-coverage curve:

| threshold | coverage | accepted precision | false-accept risk |
|---:|---:|---:|---:|
| 0.50 | 0.4200 | 0.0000 | 0.4200 |
| 0.60 | 0.4040 | 0.0000 | 0.4040 |
| 0.70 | 0.3840 | 0.0000 | 0.3840 |
| 0.80 | 0.3680 | 0.0000 | 0.3680 |
| 0.85 | 0.3530 | 0.0000 | 0.3530 |
| 0.90 | 0.3345 | 0.0000 | 0.3345 |
| 0.93 | 0.2960 | 0.0000 | 0.2960 |
| 0.95 | 0.2695 | 0.0000 | 0.2695 |
| 0.97 | 0.2420 | 0.0000 | 0.2420 |
| 0.99 | 0.2005 | 0.0000 | 0.2005 |

## End-to-End Black-Box Execution

- language spec exact: `0.8958`
- CEGIS / property verification: `0.1717`
- hidden semantic correctness: `0.1717`
- final execution correctness: `0.1717`

## Approval Gate

Explicit approved path tested: `True`.

## RuleMemory Write Safety

Writes without approval: `0`.

## Multi-Seed

- seeds: `[23001]`
- three-seed gate reached: `False`; the first seed did not satisfy the qualification threshold, so no confirmatory seeds were launched
- ID aggregate: `{"accepted_precision": {"max": 0.9184100418410042, "mean": 0.9184100418410042, "min": 0.9184100418410042, "std": 0.0}, "coverage": {"max": 0.956, "mean": 0.956, "min": 0.956, "std": 0.0}, "incorrect_confidently_accepted_rate": {"max": 0.078, "mean": 0.078, "min": 0.078, "std": 0.0}, "semantic_specification_exact": {"max": 0.878, "mean": 0.878, "min": 0.878, "std": 0.0}}`

## Decision

**OUTCOME E — LANGUAGE-TO-SPEC IS NOT RELIABLE ENOUGH**

## Recommended M-24 Integration Plan

Do not integrate either neural language parser into the trusted M-24 installation path. Keep the canonical DSL/form UI as the only trusted frontend. Retain M-23 as a research harness, and require clarification plus explicit field review for any future language proposal. The frozen backend also needs a separately approved concrete-role acquisition audit; M-23 must not silently repair its alpha-unique search limitation.

Under every future outcome, a language proposal remains untrusted until schema
validation, CEGIS, property verification, and final human approval all succeed.

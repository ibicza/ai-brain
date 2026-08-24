# M-23.1 Fair Bilingual Language-to-Spec Retest

## Checks

`Local: ruff format --check, ruff check, pytest 365 passed. Karina: ruff format --check, ruff check, pytest 364 passed before targeted fix; focused M-23.1 14 passed after fix; CUDA smoke and full official training/evaluation passed.`

## Baseline and Confounds

All 12 M-23 blocking findings were frozen, source-located, and addressed without moving `stage1-acquisition-v1`.

## Fair Dataset

Language/family MI is `0.00000000` bits; all train specs are bilingual; strict supported prompts explicitly state preserve and termination semantics.

## Model Comparison

| candidate | seed | ID raw | lexical | template | variable | order | cross | negation | composed | safe coverage | safe false accepted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| catalog_bpe | 23101 | 0.9980 | 0.2480 | 0.4300 | 0.2160 | 0.1180 | 1.0000 | 0.9740 | 0.2420 | 1.0000 | 0.0020 |
| factorized_byte | 23101 | 1.0000 | 0.4560 | 0.2940 | 0.3980 | 0.0520 | 0.9960 | 0.9280 | 0.2700 | 1.0000 | 0.0000 |
| factorized_bpe | 23101 | 1.0000 | 0.2000 | 0.3460 | 0.5600 | 0.0880 | 1.0000 | 0.9880 | 0.2340 | 0.9980 | 0.0000 |
| factorized_bpe | 23102 | 1.0000 | 0.1940 | 0.3640 | 0.6780 | 0.0760 | 1.0000 | 0.9740 | 0.1860 | 1.0000 | 0.0000 |
| factorized_bpe | 23103 | 1.0000 | 0.2260 | 0.3480 | 0.6180 | 0.0500 | 0.9960 | 0.9700 | 0.2020 | 1.0000 | 0.0000 |
| factorized_bpe_clause_shuffle | 23101 | 1.0000 | 0.5240 | 0.7320 | 0.6980 | 0.9960 | 1.0000 | 0.8140 | 0.4300 | 1.0000 | 0.0000 |
| factorized_bpe_clause_shuffle | 23102 | 1.0000 | 0.5280 | 0.7640 | 0.8960 | 1.0000 | 1.0000 | 0.9100 | 0.4600 | 1.0000 | 0.0000 |
| factorized_bpe_clause_shuffle | 23103 | 1.0000 | 0.4260 | 0.7300 | 0.6520 | 0.9960 | 1.0000 | 0.7420 | 0.3360 | 1.0000 | 0.0000 |

## Targeted Failure/Fix Iteration

| metric | baseline BPE | clause-shuffle BPE | delta |
|---|---:|---:|---:|
| order | 0.0880 | 0.9960 | +0.9080 |
| template | 0.3460 | 0.7320 | +0.3860 |
| lexical | 0.2000 | 0.5240 | +0.3240 |
| composed | 0.2340 | 0.4300 | +0.1960 |
| negation | 0.9880 | 0.8140 | -0.1740 |

## Bilingual and Safety Diagnostics

- best candidate: `factorized_bpe_clause_shuffle` seed `23101`
- RU / EN ID semantic: `1.0000` / `1.0000`; gap `0.0000`
- paired semantic equality: `1.0000`
- calibration: `CALIBRATED`
- safe coverage / incorrect accepted: `1.0000` / `0.0000`
- multi-seed: `{"candidate": "factorized_bpe_clause_shuffle", "metrics": {"test_id": {"max": 1.0, "mean": 1.0, "min": 1.0, "std": 0.0}, "test_lexical_holdout": {"max": 0.528, "mean": 0.49266666666666664, "min": 0.426, "std": 0.04716872787015663}, "test_template_holdout": {"max": 0.764, "mean": 0.742, "min": 0.73, "std": 0.015577761927397245}, "test_variable_permutation": {"max": 0.896, "mean": 0.7486666666666667, "min": 0.652, "std": 0.10585944559755744}}, "seeds": ["23101", "23102", "23103"]}`

## Clarification and Backend

- deterministic raw-text clarification resolved semantic: `1.0000`
- neural raw-text clarification resolved semantic: `1.0000`
- concrete binding property verified: `1.0000`
- accepted E2E behavior / final execution: `1.0000` / `1.0000`
- RuleMemory writes without approval: `0`
- all unsafe approval paths rejected: `True`
- explicitly approved writes: `1`

## Decision

**OUTCOME C — DETERMINISTIC CONTROLLED LANGUAGE WORKS BEST**

## Recommended M-24 Path

Use the deterministic controlled command/form frontend as the trusted path. Neural language-to-spec remains research-only and may only pre-fill a fully reviewed specification.

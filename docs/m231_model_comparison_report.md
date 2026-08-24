# M-23.1 Compute-Matched Model Comparison

The finite-answer model is labeled a catalog classifier: JSON/schema validity is guaranteed by catalog construction and is not claimed as generation ability.

## Training Budget

| candidate | seed | parameters | updates | examples | best step | wall seconds | consistency / clause-shuffle |
|---|---:|---:|---:|---:|---:|---:|---:|
| catalog_bpe | 23101 | 598881 | 4000 | 256000 | 2000 | 41.87 | 0.000 / 0.00 |
| factorized_byte | 23101 | 534449 | 7000 | 448000 | 5000 | 414.64 | 0.000 / 0.00 |
| factorized_bpe | 23101 | 592689 | 5000 | 320000 | 3000 | 67.38 | 0.000 / 0.00 |
| factorized_bpe | 23102 | 592689 | 5500 | 352000 | 3500 | 75.73 | 0.000 / 0.00 |
| factorized_bpe | 23103 | 592689 | 6000 | 384000 | 4000 | 79.62 | 0.000 / 0.00 |
| factorized_bpe_clause_shuffle | 23101 | 592689 | 10500 | 672000 | 8500 | 148.74 | 0.000 / 0.75 |
| factorized_bpe_clause_shuffle | 23102 | 592689 | 8000 | 512000 | 6000 | 113.42 | 0.000 / 0.75 |
| factorized_bpe_clause_shuffle | 23103 | 592689 | 7000 | 448000 | 5000 | 102.16 | 0.000 / 0.75 |

All neural candidates used the same maximum update budget, batch size, optimizer, and 500-step validation cadence. Early stopping produced different processed-example and wall-time totals, so the table supports diagnostic comparison only; it does not establish architecture superiority.

## Diagnostic Ladder

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

Best ranked candidate: `factorized_bpe_clause_shuffle` seed `23101`.

Deterministic train-lexicon lexical holdout: `0.1680`.
Extended production parser lexical holdout: `1.0000` (programmed support, not OOD learning).

## Targeted Failure/Fix Iteration

The retained fix permutes only complete clauses already present in train. It adds no heldout lexeme or template ID and leaves calibration risk at `.01`.

| metric | baseline BPE | clause-shuffle BPE | delta |
|---|---:|---:|---:|
| order | 0.0880 | 0.9960 | +0.9080 |
| template | 0.3460 | 0.7320 | +0.3860 |
| lexical | 0.2000 | 0.5240 | +0.3240 |
| composed | 0.2340 | 0.4300 | +0.1960 |
| negation | 0.9880 | 0.8140 | -0.1740 |

# M-23.1 Calibration and Safety Report

- best candidate: `factorized_bpe_clause_shuffle`
- calibration status: `CALIBRATED`
- confidence method: `product`
- threshold: `0.29435169557596`
- calibration coverage: `0.7000`
- calibration accepted precision: `1.0000`
- safe ID coverage: `1.0000`
- safe ID incorrect accepted rate: `0.0000`

If no non-empty threshold has conditional risk <= .01, status is `FAILED`, coverage is zero, and every supported neural proposal becomes review-required/ambiguous.

## Confidence Frontier

| confidence | best coverage at conditional risk <= .01 | threshold | accepted | conditional risk |
|---|---:|---:|---:|---:|
| product | 0.7000 | 0.294352 | 1400 | 0.0000 |
| minimum | 0.7000 | 0.542630 | 1400 | 0.0000 |
| temperature_joint | 0.7000 | 0.148213 | 1400 | 0.0000 |

## ID Group Risk

| dimension | value | count | semantic exact | coverage | incorrect accepted / population |
|---|---|---:|---:|---:|---:|
| language | en | 250 | 1.0000 | 1.0000 | 0.0000 |
| language | ru | 250 | 1.0000 | 1.0000 | 0.0000 |
| family | CLEAR | 84 | 1.0000 | 1.0000 | 0.0000 |
| family | DRAIN | 84 | 1.0000 | 1.0000 | 0.0000 |
| family | DROP_THEN_TRANSFER | 82 | 1.0000 | 1.0000 | 0.0000 |
| family | MERGE_THREE | 82 | 1.0000 | 1.0000 | 0.0000 |
| family | MERGE_TWO | 84 | 1.0000 | 1.0000 | 0.0000 |
| family | NOOP | 84 | 1.0000 | 1.0000 | 0.0000 |

## OOD Risk

| split | coverage | incorrect accepted / population | conditional accepted risk |
|---|---:|---:|---:|
| test_id | 1.0000 | 0.0000 | 0.0000 |
| test_lexical_holdout | 0.6560 | 0.1420 | 0.2165 |
| test_template_holdout | 0.8020 | 0.0760 | 0.0948 |
| test_variable_permutation | 0.7780 | 0.0940 | 0.1208 |
| test_order_holdout | 0.9980 | 0.0020 | 0.0020 |
| test_cross_language | 1.0000 | 0.0000 | 0.0000 |
| test_negation_preserve | 0.8200 | 0.0140 | 0.0171 |
| test_ambiguous | 0.0000 | 0.0000 | 0.0000 |
| test_contradictory | 0.0000 | 0.0000 | 0.0000 |
| test_unsupported | 0.0000 | 0.0000 | 0.0000 |
| test_composed_ood | 0.5460 | 0.1220 | 0.2234 |

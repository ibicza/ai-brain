# M-25.1 Novelty Report

## Calibration

Threshold `0.64675544` was selected only from calibration with requested false-known bound `0.05`. Blind was not used for threshold or recipe selection.

## Blind Metrics

| Metric | Result |
|---|---:|
| known recall | 0.8292 |
| unknown abstention | 0.9530 |
| ambiguous abstention | 0.9840 |
| false-known | 0.0470 |
| false-unknown | 0.1708 |
| AUROC | 0.9656 |
| AUPRC | 0.9931 |
| risk at 80% coverage | 0.0505 |

Per-family false-known is highest for copy-without-consume `0.2468`, register E `0.1286`, and swap `0.1231`. Compare is `0.0132`, multiply `0.0357`, missing destination `0.0411`, obscured role `0.0107`, while conditional, sort, and missing source are `0`.

The aggregate bound passes, but weak unknown families prohibit automatic use. Learned retrieval always returns review candidates or synthesis/clarification; it cannot set exact evidence, execute, or write RuleMemory.

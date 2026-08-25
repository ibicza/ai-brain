# M-25 Novelty and Abstention Report

## Calibration

Unknown/ambiguous examples are explicit dataset classes, not random distractors. Threshold selection used only the calibration split, with development used for recipe choice. Blind request/target hashes were frozen first and hidden targets remained unopened until the three-seed recipe hash was written.

The initial 0.05 calibration bound generalized poorly enough to miss the research target on development, so it was rejected. The final 0.02 bound produced per-seed thresholds 0.75936, 0.72859, and 0.72263.

## Final Results

| Surface | known recall | unknown abstention | false-known | false-unknown | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| calibration, seed 25101 | 1.0000 | 0.9813 | 0.0187 | 0.0000 | 1.0000 | 1.0000 |
| development, 3-seed mean | 1.0000 | 0.9749 | 0.0251 | 0.0000 | 1.0000 | 1.0000 |
| blind, 3-seed mean | 1.0000 | 0.9662 | 0.0338 | 0.0000 | 1.0000 | 1.0000 |

Blind unknown abstention exceeded the 0.95 research target for every seed. False-known remained below 0.05 for every seed. Risk at 80% known-query coverage was zero because every covered known query ranked its target first.

## Fail-Closed Policy

Threshold crossing never authorizes execution. Above threshold means `REVIEW_CANDIDATES`; below threshold means `RUN_SYNTHESIS`. Both require a later exact specification/controlled confirmation or explicit reviewed selection plus confirmation. Ambiguous structured fields use deterministic clarification targets; unknown requests never fall through to nearest-skill execution.

The threshold is therefore a usability calibration, not part of the trusted execution proof. If deployment distribution shifts, the safe fallback is candidate review for all assistive queries; exact structured and controlled paths remain unaffected.

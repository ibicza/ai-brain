# M-25 Retrieval Confounds Audit

## Frozen Evidence

- audited commit: `af15e11f0ba1d5ea8b28d0b4b45d388b459819de`
- original registry hash: `774020a7ad25e53121beccea0067d05bddab5b6726adaa725724518ae261c624`
- recipe hash: `b6c7e58a1cc97f66e9beb019109694b1442795dfce1907f8524607822fd17689`
- blind public hash: `61f01d95d3c3a9cfcd859981b6f26a973bb1ec12022e8115696a95df7dd7534b`
- blind target hash: `34bce9e034b0c1b4cecd1ef1972749e7236339a160b62e975c1c008c2cfc41f3`
- train/validation/calibration/development hashes: `119c81ee...`, `3672e459...`, `85ea7e80...`, `9c0a0427...`

The original three-seed blind result was top1/top5/hard top1 `1.0000`, unknown abstention `0.9662 +/- 0.0064`, and false-known `0.0338 +/- 0.0064`.

## Measured Confounds

Every known V1 query contains a complete catalog alias or controlled example as a substring: train `16,100/16,100`, validation `1,618/1,618`, calibration `1,573/1,573`, and development `3,215/3,215`. The skill tower encodes those same strings.

The V1 OOD labels change wrappers rather than reserving lexemes, templates, assignments, or query-free skills. Negative-only qualifiers explicitly announce uncertainty or catalog absence. `HARD_NEIGHBOR` adds a warning to a normal positive surface instead of changing one semantic field. Semantic lookup delegates to structural hash lookup. Only one DRAIN skill completed selection through execution.

## Classification

| M-25 claim | Classification | M-25.1 treatment |
|---|---|---|
| 89/89 exact structured retrieval | TRUSTED_VALID | regression gate |
| 356/356 controlled RU/EN | TRUSTED_VALID | regression gate |
| hash-bound confirmation and dispatch rejection | TRUSTED_VALID | expanded security gate |
| single DRAIN end-to-end dispatch | INTEGRATION_VALID | expanded to 89/89 |
| deterministic V1 rankings | DEVELOPMENT_DIAGNOSTIC | rerun on V2 |
| learned top1/top5/hard metrics | CONFOUNDED | discarded as OOD evidence |
| V1 novelty calibration | CONFOUNDED | rebuilt without negative clues |
| lexical/template/variable/order generalization | NOT_TESTED | real V2 holdouts |
| zero-query-skill retrieval | NOT_TESTED | 18-skill V2 slice |
| semantic equivalence classes | NOT_TESTED | true effect classes |

The trusted architecture remains valid. The original learned generalization claim does not.

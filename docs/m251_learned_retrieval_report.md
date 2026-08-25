# M-25.1 Learned Retrieval Report

## Development Selection

The unchanged sanitized M-25 bi-encoder on V2 reached top1/top5 `0.8234/0.8929`, hard pairwise `0.9193`, zero-query top1/top5 `0.3938/0.6850`, and false-known `0.0486`.

Explicit hard-negative loss was tested once and regressed top1/top5 to `0.8191/0.8800` with false-known `0.0624`. No mining round was run because the declared neighbors already covered the observed errors and the explicit loss did not help.

One permitted targeted fix normalized train/catalog operation lexemes and register roles into explicit hashed features. Blind-only true-OOD lexemes were excluded. The targeted development result was top1/top5 `0.8263/0.9114`, hard pairwise `0.9321`, zero-query top5 `0.7967`, and false-known `0.0413`; it became the primary recipe.

The multi-seed gate failed because development top5 was below `0.95`. Only seed `25101` was opened.

## Frozen Blind

Recipe hash: `6a30ea6b11c0e0c5b147da50dd4bdf02edad382f8a5c558bb3e80609bbd5510d`.

| Slice | top1 | top5 |
|---|---:|---:|
| ID | 1.0000 | 1.0000 |
| catalog lexical | 1.0000 | 1.0000 |
| true lexical OOD | 0.9560 | 0.9940 |
| template holdout | 1.0000 | 1.0000 |
| order holdout | 1.0000 | 1.0000 |
| cross-language transfer | 1.0000 | 1.0000 |
| composed OOD | 0.8360 | 0.9580 |
| hard neighbor | 0.7140 | 0.8800 |
| variable permutation | 0.1500 | 0.4660 |
| zero-query skill | 0.3900 | 0.7820 |

Overall top1/top5 is `0.8046/0.9080`. The model generalizes across heldout wording and syntax, but not across unseen structural bindings. It is useful for reviewed candidate suggestions, not trustworthy selection.

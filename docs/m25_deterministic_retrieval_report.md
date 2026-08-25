# M-25 Deterministic Retrieval Report

## Trusted Results

| Path | Result |
|---|---:|
| exact structured specification | 89 / 89 |
| exact semantic signature | 89 / 89 in tests |
| frozen controlled RU/EN matrix | 356 / 356 |
| controlled RU/EN skill equality | 1.0000 |
| unknown automatic selections | 0 / 785 |
| assistive results marked exact | 0 / 785 |

All exact paths validate the current registry against the complete RuleMemory fingerprint before selecting. The controlled path uses no fuzzy retriever.

## Assistive Development Baselines

| Method | top1 | top3 | top5 | MRR | hard-neighbor top1 |
|---|---:|---:|---:|---:|---:|
| lexical token overlap | 0.0625 | 0.1726 | 0.2737 | 0.1395 | 0.0458 |
| BM25-style | 0.1891 | 0.5711 | 0.8156 | 0.4088 | 0.1494 |
| character n-gram | 0.9925 | 1.0000 | 1.0000 | 0.9962 | 0.9920 |

These are proposal baselines, not selectors. Character n-grams are unusually strong because the controlled structural domain makes operation and register strings highly informative. Its remaining error rates are family 0.0040, register 0.0075, destination 0, and order 0.0075.

Mean query latency in the safety-first non-cached implementation is 23.68 ms lexical, 24.49 ms BM25, and 29.87 ms character n-gram. Controlled RU/EN latency was approximately 106 ms because each acceptance query reloaded and revalidated the durable stores.

## Scale

Unique skills remain 89 while metadata/index surfaces grow. At 10,000 text entries, the synthetic lexical index built in 1,318 ms, queried in 8.90 ms, and peaked at 46.8 MB. Counts are reported separately; text entries are never presented as unique skills.

## Decision

Exact specification and controlled-language routes satisfy trusted-release targets. Character n-gram retrieval is a useful assistive fallback, but it remains review-only regardless of score.

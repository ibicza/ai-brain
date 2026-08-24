# M-23.1 Tokenization and Truncation Report

| encoder | average | p95 | max | configured max | truncated |
|---|---:|---:|---:|---:|---:|
| UTF-8 byte | 236.01 | 449 | 572 | 768 | 0 |
| bilingual BPE | 53.67 | 93 | 130 | 256 | 0 |

Both paths prepend an explicit summary/BOS token. Overlength input raises `InputTooLongError`; no semantic clause is silently cut.

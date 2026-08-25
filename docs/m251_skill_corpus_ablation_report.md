# M-25.1 Skill Corpus Ablation Report

## Conditions

- `rich`: production names, aliases, examples, summary, and schema.
- `sanitized`: normalized effect/action/role fields without aliases or query examples.
- `minimal`: compact typed phases and role sets only.

Complete query-to-corpus line overlap is zero in every condition. Development mean character four-gram overlap is `0.0588` rich, `0.0151` sanitized, and `0.0026` minimal.

## Blind Results

| Corpus | top1 | top5 | hard top1 | zero top1/top5 | variable top1/top5 | false-known |
|---|---:|---:|---:|---:|---:|---:|
| rich | 0.8450 | 0.9600 | 0.7420 | 0.5860 / 0.8380 | 0.2900 / 0.8520 | 0.0410 |
| sanitized targeted | 0.8046 | 0.9080 | 0.7140 | 0.3900 / 0.7820 | 0.1500 / 0.4660 | 0.0470 |
| minimal | 0.7496 | 0.8054 | 0.6220 | 0.0820 / 0.3180 | 0.0000 / 0.0940 | 0.0430 |

Rich metadata provides a substantial advantage, especially on unseen skill assignments. Sanitized remains strong on language and templates but does not learn robust structural composition. Minimal fails query-to-symbol alignment for query-free skills.

The primary fair claim uses sanitized, not rich. Rich is retained as a realistic catalog-matching baseline.

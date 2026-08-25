# M-25 Learned Retrieval Report

## Model and Trust Policy

The research model is a bilingual bi-encoder with separate query and skill towers. Input is a deterministic hashed character 2-5-gram plus word-feature vector; each tower uses a 4,096 -> 128 -> 96 projection with GELU and L2 normalization. The model has 1,073,600 parameters and trains with contrastive cross-entropy over all 89 skill descriptions plus sampled query batches.

Skill encoder text includes bilingual names, effect summary, exact effect schema, aliases, and examples. It contains no skill IDs or rule IDs. The learned module is excluded from trusted imports and has no RuleMemory write or execution API. Its outputs are always assistive and non-exact.

## Recipe Selection

Seed 25101 with calibration false-known bound 0.05 was rejected before blind opening because development false-known was 0.0611 and abstention 0.9389. The selected recipe tightened the calibration bound to 0.02 without changing architecture or inspecting blind targets.

Selected configuration: 1,500 steps, batch 128, learning rate 0.002, temperature 0.08, seeds 25101/25102/25103 on Karina RTX 5060. Seed 25101 passed the multi-seed gate first: development top5 1.0, hard-neighbor top1 1.0, and false-known 0.0242.

## Development

Across all three confirmed seeds, top1, top3, top5, MRR, and hard-neighbor top1 were 1.0000. Mean unknown abstention was 0.9749, minimum 0.9682; mean false-known was 0.0251. Known recall was 1.0000 and risk at 80% coverage was 0.

## Frozen Blind Result

Recipe hash: `b6c7e58a1cc97f66e9beb019109694b1442795dfce1907f8524607822fd17689`.

| Metric | mean | std | min | max |
|---|---:|---:|---:|---:|
| top1 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| top5 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| hard-neighbor top1 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| unknown abstention | 0.9662 | 0.0064 | 0.9577 | 0.9731 |
| false-known | 0.0338 | 0.0064 | 0.0269 | 0.0423 |

Each seed also achieved known recall, AUROC, and AUPRC of 1.0000, zero known ranking failures, zero RU/EN top1 gap, and zero risk at 80% coverage.

## Cross-Language Ranking

For all 89 canonical RU/EN pairs and all three seeds, top1 skill equality was 1.0000. Mean top5 Jaccard overlap was 0.6948, while exact top5 order equality was only 0.0300. Thus the selected skill is invariant, but lower-ranked near-neighbor ordering is language-sensitive and must remain assistive. Batched neural latency averaged about 0.98 ms RU and 0.85 ms EN per query on Karina.

## Reranker Decision

No cross-encoder reranker was trained. The bi-encoder already reached perfect known top1/top5 and hard-neighbor top1; a reranker cannot improve those metrics and would add complexity to a non-trusted path. Lower-rank cross-language order remains documented rather than hidden.

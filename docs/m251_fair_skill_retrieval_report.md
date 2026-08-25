# M-25.1 Fair Skill Retrieval Report

## Decision

**Outcome B: trusted routing works; learned compositional OOD does not.**

The learned retriever is strong on heldout lexical/syntactic surfaces and safe aggregate abstention, but misses the zero-query, variable-binding, and counterfactual goals. Keep neural, lexical, and n-gram retrieval as experimental candidate suggestions only. Proceed to factual memory without promoting learned retrieval to trusted selection.

## Checks

- branch: `exp/stage2-skill-registry-fair-retest`
- local full pytest: 493 passed
- local full V2 acceptance: PASS
- Karina: RTX 5060 Laptop GPU, 8 GB
- fair learned recipe opened once: VALID
- Stage-1 source changed: no
- trusted import without torch: PASS
- final exact SHA and clean-status transcripts: `runs/m251_final_gate/`

## Trusted Results

| Gate | Result |
|---|---:|
| structural exact | 89/89 |
| semantic classes | 57/57 |
| controlled RU/EN | 356/356 |
| trusted language equality | 1.0000 |
| full dispatch | 89/89 |
| representative state battery | 42/42 |
| controlled representative dispatch | 12/12 |
| unsafe automatic selection | 0 |

Semantic classes comprise 41 singletons, 12 two-member MERGE_TWO classes, and 4 six-member MERGE_THREE classes. All 24 DROP_THEN_TRANSFER classes preserve order.

## Fair Dataset

V2 uses `24k/3k/3k/6k/6k`, 18 balanced zero-query skills, real lexical/template/assignment/language/order holdouts, genuine one-field counterfactuals, and physically separated blind targets. Pairwise prompt intersections and complete blind catalog substrings are zero. Development wrapper and shape AUROC are `0.5016` and `0.5720`; blind values are `0.4857` and `0.5788`.

## Learned Result

Primary sanitized blind top1/top5 is `0.8046/0.9080`. ID/catalog/template/order/cross-language are `1.0000`; true lexical OOD is `0.9560`; composed OOD is `0.8360`. Hard top1/switch is `0.7140`, variable top1/top5 `0.1500/0.4660`, and zero-query `0.3900/0.7820`.

Unknown abstention is `0.9530`, false-known `0.0470`, AUROC `0.9656`. Family-specific copy/register-E/swap errors remain too high for any authoritative use.

## Recommendation

Retain the production boundary:

`SkillRegistry + exact specification/controlled/semantic routing + explicit confirmation + frozen Stage-1 dispatch`.

Use learned ranking only to populate a human-reviewed candidate list. The next milestone may proceed to factual memory; do not claim broad compositional skill retrieval from M-25.1.

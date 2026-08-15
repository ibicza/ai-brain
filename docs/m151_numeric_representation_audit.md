# M-15.1 Numeric Representation Audit

## Sources Checked

- Abacus / digit-position embeddings: [Transformers Can Do Arithmetic with the Right Embeddings](https://arxiv.org/pdf/2405.17399)
- Abacus reference implementation: [mcleish7/arithmetic](https://github.com/mcleish7/arithmetic)
- Position Coupling: [Position Coupling: Improving Length Generalization of Arithmetic Transformers](https://proceedings.neurips.cc/paper_files/paper/2024/hash/27aa3a0e6d63db269977bb2df5607cb8-Abstract-Conference.html)
- Arithmetic tokenization: [Tokenization counts: the impact of tokenization on arithmetic in frontier LLMs](https://arxiv.org/abs/2402.14903)

## Tokenizer Audit

Tokenizer: `artifacts/tokenizers/stage1_bpe_8k.json`

For numbers `0..999` with default BPE:

| Token count | Number count |
|---:|---:|
| 1 | 105 |
| 2 | 895 |

For `digit_safe` tokenization:

| Token count | Number count |
|---:|---:|
| 1 | 10 |
| 2 | 90 |
| 3 | 900 |

Digits `0..9` are stable single tokens in the current tokenizer.

Key finding: default BPE merges many multi-digit numbers. M-15 feature extraction assigned one majority digit/place/role label per BPE token, so a token like `73` could only receive one feature tuple even though it represents two arithmetic digits. That is a real representation mismatch.

## Feature Alignment

For default BPE, alignment is exact at token offset level, but multi-digit tokens collapse multiple digit characters into one token-level feature. This is not an indexing bug, but it is a semantic bottleneck.

For `digit_safe`, decimal spans are split into stable digit tokens while normal text still uses BPE. Decode round-trip is preserved:

```text
73 -> [token("7"), token("3")] -> "73"
149 -> [token("1"), token("4"), token("9")] -> "149"
```

Abacus position IDs use arithmetic significance:

```text
71 -> 7:P1, 1:P0
63 -> 6:P1, 3:P0
134 -> 1:P2, 3:P1, 4:P0
```

Position Coupling additionally maps compact trace rows by arithmetic role:

```text
U 1 3 0 -> 4 0
  operands/result use units position; carry-out uses tens position

T 7 6 0 -> 3 1
  operands/result use tens position; carry-out uses hundreds position
```

## Partial Generation Behavior

Partial compact traces no longer require the full answer to exist before assigning features. However, a malformed generated trace can still create misleading generic numeric spans. Example: repeated chunks like `4052 4052` are valid decimal spans for digit-safe/Abacus extraction even when the trace grammar is wrong.

This is not an off-by-one alignment bug. It is an autoregressive feedback risk: once generation leaves the compact trace grammar, subsequent feature extraction can still attach numeric-position IDs to malformed spans.

## Embedding Norm Audit

Mean row norms at numeric tiny initialization, seq256:

| Embedding | Mean row norm |
|---|---:|
| token | 11.2751 |
| position | 11.2522 |
| digit value | 10.3076 |
| digit place | 8.7816 |
| number role | 10.0583 |
| operation step | 9.9656 |

M-15 additive numeric checkpoint, seq128:

| Embedding | Mean row norm |
|---|---:|
| token | 10.6231 |
| position | 10.5394 |
| digit value | 9.9053 |
| digit place | 8.8010 |
| number role | 9.0564 |
| operation step | 9.5201 |

The additive feature branches are similar in scale to token and position embeddings. M-15 therefore injected several random learned branches at nearly full representation magnitude from the start. This supports the hypothesis that M-15 tested an overly strong perturbation, not the entire idea of numeric bias.

## Bugs And Confounds Found

- Default BPE merges multi-digit numbers, while M-15 features assume digit-level arithmetic structure.
- `digit_safe` sees every decimal span, including digits inside task labels such as `ADD2_COMPOSED`. This is expected behavior but should be kept in mind for future data format cleanup.
- M-15 staged continuation used seq128 -> seq256, which skipped `position_embedding.weight` during checkpoint loading. M-16 uses seq256 from the start for all comparable runs.
- No direct offset bug was found in feature alignment; the major issue is representation granularity and malformed-generation feedback risk.

## Fixes Before M-16

- Added opt-in `numeric_tokenization=digit_safe`.
- Added separate Abacus and coupled position feature tensors.
- Added `abacus_*`, `coupled_*`, and `gated_place_*` model configs instead of reusing the full M-15 additive feature cocktail.
- Kept old datasets/checkpoints compatible by backfilling missing feature tensors with `NONE=0`.

# M-16 Numeric Position Generalization Ablation Report

## Checks

- Device: `cuda:0`, NVIDIA GeForce RTX 3050 Laptop GPU
- Base references: M-14 best digit holdout `0.8100`, 2digit holdout-combo `0.0645`, far `0.0175`
- Training: tiny only, `train_mixed.jsonl`, seed `41600`, batch `8`, seq `256`, steps `8000`, answer-only loss
- No shifted priming, no broad curriculum, no big model

Final checks after implementation are recorded in the task closeout.

## Implementation Summary

Implemented `numeric_tokenization`:

- `default_bpe`: existing tokenizer behavior
- `digit_safe`: normal text stays BPE, decimal spans are forced into stable digit tokens

Implemented clean model variants:

- A `tiny`: default BPE baseline
- B `tiny`: digit-safe tokenization only
- C `abacus_tiny`: digit-safe + Abacus-style digit-position embedding with train random offset `0..99`
- D `coupled_tiny`: digit-safe + task-relative coupled position IDs
- E `gated_place_tiny`: digit-safe + `alpha * place_embedding`, alpha starts at `0`

## Main Table

Primary metric: final normalized exact match.

| Variant | Tokenization | Position method | Extra params | Digit holdout | 2digit same | 2digit holdout-combo | 2digit far | Delta vs M-14 holdout/far | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| A baseline | default BPE | none | 0 | 0.1025 | 0.5730 | 0.0210 | 0.0195 | -0.0435 / +0.0020 | same-range memorization, weak OOD |
| B digit-safe | digit-safe | none | 0 | 0.1188 | 1.0000 | 0.0525 | 0.1815 | -0.0120 / +0.1640 | main improvement, but add OOD still 0 |
| C Abacus | digit-safe | digit position | 65,536 | 0.1013 | 0.8525 | 0.0550 | 0.1865 | -0.0095 / +0.1690 | tiny holdout gain over B, still add OOD 0 |
| D Position Coupling | digit-safe | coupled position | 65,536 | 0.2863 | 0.1550 | 0.0445 | 0.1115 | -0.0200 / +0.0940 | helps digit table, hurts composition |
| E Gated place | digit-safe | gated place-only | 641 | 0.1300 | 0.9160 | 0.0580 | 0.1485 | -0.0065 / +0.1310 | best holdout, near-strong far, add OOD 0 |

## Add/Sub Split

2digit holdout-combo:

| Variant | Add final NEM | Sub final NEM |
|---|---:|---:|
| A baseline | 0.0000 | 0.0433 |
| B digit-safe | 0.0000 | 0.1082 |
| C Abacus | 0.0000 | 0.1134 |
| D Position Coupling | 0.0000 | 0.0918 |
| E Gated place | 0.0000 | 0.1196 |

2digit far:

| Variant | Add final NEM | Sub final NEM |
|---|---:|---:|
| A baseline | 0.0000 | 0.0388 |
| B digit-safe | 0.0000 | 0.3612 |
| C Abacus | 0.0000 | 0.3711 |
| D Position Coupling | 0.0000 | 0.2219 |
| E Gated place | 0.0000 | 0.2955 |

The headline result is asymmetric: digit-safe/Abacus/Gated improve far-range subtraction, but no tested representation transfers addition to held-out or far splits.

## Tokenizer And Alignment Findings

The current BPE tokenizer uses stable single tokens for digits `0..9`, but default BPE represents `0..999` as:

- 105 numbers with one token
- 895 numbers with two tokens

This conflicts with digit-level feature assumptions. `digit_safe` fixes this for decimal spans and preserves decode round-trip.

Feature alignment was not shifted relative to BPE offsets. The problem was not an indexing bug; it was merged-token granularity plus autoregressive feedback risk on malformed traces.

## Embedding Norm Findings

M-15 additive branches had mean row norms close to token/position embeddings. This makes M-15 a test of a strong random additive perturbation:

```text
token mean row norm:          ~11.28 at init
position mean row norm:       ~11.25 at init
digit/role/step branches:      ~8.78..10.31 at init
```

Gated place-only did not collapse like M-15: same-range composition reached `0.9160`, and holdout-combo reached `0.0580`. That suggests M-15's degradation was at least partly caused by the heavy random additive cocktail.

## Abacus Details

Implemented close to the Abacus idea:

- digits receive position IDs by significance inside a decimal span
- units = P0, tens = P1, hundreds = P2
- train examples use deterministic random offsets up to `99`
- eval uses offset `0`

Adaptation note: the current compact traces are normal-order text, not a full least-significant-digit-first dataset. Abacus therefore acts as an added learned digit-significance bias rather than a full reproduction of the paper's full data recipe.

Result: Abacus slightly improved far and holdout over digit-safe, but did not fix addition OOD.

## Position Coupling Details

Implemented task-relative coupled IDs for compact arithmetic traces:

- U rows map operand/result digits to units position
- T rows map operand/result digits to tens position
- carry/borrow out maps to the next significance

This improved digit-table holdout to `0.2863`, the best digit-table result in M-16, but composition same dropped to `0.1550`. Current coupling therefore over-biases or misroutes the compact trace for multi-digit generation.

## Failure Pattern

All variants have `0.0000` add final NEM on 2digit holdout-combo and far. Subtraction carries all OOD gains.

Interpretation:

- digit-safe tokenization is a real improvement;
- same-range composition can be learned very well;
- held-out/far addition remains unsolved;
- position bias alone, in these variants, does not create robust add composition transfer.

## Recurrent/Input Injection

Not tested in this milestone. The condition from the task was to test recurrent/input injection only after a representation winner exists. The best representations improve subtraction OOD but do not solve addition OOD, so recurrence would be confounded here.

## Final Verdict

Verdict A with caveat: `digit-safe tokenization was the main fix`.

It materially improves same-range composition and far-range subtraction, and it is the core enabler for all better runs. However, because addition OOD remains at `0.0`, this is not a complete arithmetic-composition solution.

Recommended next step:

1. Keep digit-safe tokenization.
2. Split add and sub composition into separate curricula.
3. Focus on addition carry/output-length transfer specifically.
4. Revisit coupled/Abacus only after the add-specific failure is isolated.

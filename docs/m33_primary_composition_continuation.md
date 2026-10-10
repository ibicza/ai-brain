# Own compositional continuation, 2026-10-10

This continues the developmental procedural course, not M33 closure, animal
recognition, photographic generalization or a language model. No candidate is
activated. The authoritative workbook and existing concept IDs are unchanged:
this block needs no new lexical meanings. Animal/fruit parts remain planned.

## Changes and preregistered boundary

V3 continues the exact V2 curriculum checkpoint with 4,500 training scenes and
480 each for development, calibration, ordinary final, held combinations and
style transfer. Eighty percent of non-transfer scenes use random orientations,
elliptical spots, stripe directions and textured/gradient backgrounds; twenty
percent retain the older simple renderer. Wave stripes and irregular polygonal
spots occur only in transfer. Joint and curriculum each get 9,000 steps from
the same candidate; selection uses balanced development cross-entropy alone.

V3 fails complete descriptions: shape/pattern thresholds are disabled.
Development diagnostics exposed nearly white-on-white or black-on-black marks
in the generator. Old images, labels and results were not rewritten or
reclassified to excuse failures.

V4 continues the V3 joint checkpoint with 9,000 training scenes, 600 per other
cohort and 9,000 steps per schedule. Its *new* generator ensures visible contrast
on white/black surfaces; backgrounds, positions and orientations remain varied,
with some upright examples. Waves and irregular spots stay out of training.
Green oval and blue square pairs remain excluded from this composition course's
train/dev/calibration sets. This does not imply their absence from every earlier
foundational course in inherited weights. All splits share a procedural renderer
family, not independent photographic sources or an external blind exam.

An optional spatial readout retains a learned 6x6 input-grid representation. It
adds 722,800 parameters, bringing new trainable parameters to 923,232; 974,889
inherited parameters remain frozen. Zero-output initialization preserves the
preceding forward function exactly, tested before training. There is one own
inherited causal core. Only RGB and bounded RU/EN question tokens enter inference,
never renderer masks, labels, gold boxes or object identities. Candidate loading
is strict; warm loading allows only the tested function-preserving extension.

V4 strengthens acceptance: zero accepted errors; at least 80% positive recall
per task, 90% unknown recall, 80% complete visible descriptions and two-target
binding; no accepted blank-image answers. This is an empirical screen, not a
probability guarantee or production admission. Thresholds use only separate
calibration; failing tasks abstain. Final cohorts cannot choose weights/policy.

V5 continues V4 with a fresh seed and the same sizes, capacity and strict screen.
For shape questions only, the network receives an edge-magnitude view computed
from RGB differences, invariant to channel permutation and intensity inversion.
The question gate uses supported input words, not renderer labels; there are no
gold masks or hand-written geometric classification rules. This is intentionally
a changed shape-input function, not a function-preserving claim. Non-shape
questions keep RGB; legacy inference remains delegated unchanged. Smoothed
supervision (0.02) averages only permitted answers, avoiding the -infinity values
used to mask other tasks. Neither edge views nor smoothing establish correctness
without evaluation.

## Evidence and comparison

Local evidence roots:

- `D:\ai-brain-data\visual-lexicon\composition-20261010-v3`
- `D:\ai-brain-data\visual-lexicon\composition-20261010-v4`
- `D:\ai-brain-data\visual-lexicon\composition-20261010-v5`

Remote roots are the corresponding `m33-composition-20261010-v3`, `-v4`, `-v5` under
`/home/ibicza/ai-brain/runs`. Each preserves source capsule, exact dataset arrays,
records, both best checkpoints, selection/policy freezes, probabilities,
descriptions, legacy checks and replay receipt.

Separate arithmetic repeats inference, task/overall metrics, full descriptions,
target binding and actual blank-image outputs. It checks question/pixel/oracle
correspondence and binds the source manifest to the archive. Supplemental
verification stays outside old frozen sources. An initial supplemental constructor
incompatibility was fixed without rewriting old code; its failed executed copy
is retained. Tests cover backwards replay and hostile manifest, lineage,
threshold, raw-metric and blank-result modifications.

Repeated NPZ decompression in the verification loop was corrected by loading
each sealed array once. A regression test counts accesses and forbids a return
to per-question decompression. Old validation eventually completed unchanged;
the optimized supplemental verifier runs outside its capsule and preserves all
checks. A simultaneous recovery attempt safely refused an already-created receipt;
no original source, result or process was replaced.

Past V2/V3 models and their **original frozen policies** are compared on V4's
exact same new final pixels, without retuning calibration. This measures
improvement but cannot isolate the individual effects of more data, contrast
repair and capacity. Numeric results reside in the catalogue artifacts
`composition_result_v3.json`, `composition_result_v4.json` and
`composition_comparison_v4.json`.
V5 likewise compares past V2/V3/V4 policies on its own exact new final pixels;
its comparison is stored in `composition_comparison_v5.json`.

## Measured outcome

V5 selects the curriculum step 7,800 by balanced dev CE 0.018880, versus
0.019146 for joint. All three calibration thresholds are 0.9; they are not
adjusted after final evaluation. All candidate weights remain experimental.

| V5 cohort | Positive recall after refusal | Complete correct visible descriptions | Accepted errors |
| --- | ---: | ---: | ---: |
| Ordinary final | 99.42% | 98.44% | 0 / 3,254 |
| Held color-shape combinations | 99.36% | 98.08% | 1 / 3,253 |
| New waves/irregular spots | 97.46% | 92.48% | 5 / 3,195 |

Each cohort has 600 scenes, 3,600 questions and 1,091 fully visible objects.
All five style-transfer errors are pattern answers. The held-pair error is a
shape answer. Color makes no accepted errors; shape makes none on ordinary/style
finals. These measurements do not certify future sources.
Unknown recall is 100% and blank-image accepted answers are zero in this screen.
Status remains **NEEDS_WORK_NOT_PRODUCTION**: the zero-error requirement is
not relaxed. Complete descriptions still mean only color/shape/pattern, never
the object's species/name or anatomy.

On exactly V5's final pixels, V2/V3/V4 ordinary accepted errors are 255/0/3,
and positive recalls are 39.93%/33.18%/66.27%; their complete-description rates
are all zero. V5 therefore increases useful coverage, rather than merely
refusing more answers. This comparison is not a causal ablation or blind exam.

400 course/catalogue tests pass after the final geometry guard, two skip; V5's sealed pre-training
subset passes 51 tests remotely. Separate inference/arithmetic replay succeeds.
Original own tensors remain byte-identical, with exact delegated legacy logits
on six examples for each of seven tasks, not a complete new old-skill exam.

Final code review also found that the old radius limit of 16 pixels plus center
jitter could clip a rotated square corner by <1 pixel. The future generator limit
is 15 pixels, proving positive border/half-plane clearance even at 45 degrees;
a regression test checks these bounds. Existing V3-V5 arrays/results and frozen
generators are unchanged. Reported visible-object eligibility follows their
oracle visibility flags; it is not independent full-contour annotation.

Next boundary: develop pattern uncertainty, rare held-shape errors and style diversity without using
these known finals as new blind tests; freeze a new candidate before fresh
evaluation. Only after separate real-source controls should object/part images,
such as watermelon and giraffe anatomy, be admitted for the next block.

## Research and limits

[Domain randomization](https://arxiv.org/abs/1703.06907) motivates varied rendering,
not a claim of demonstrated photographic transfer here.
[Selective classification](https://arxiv.org/abs/1705.08500) motivates measuring
error alongside answer coverage. Our calibration grid is a bounded empirical
heuristic, not that paper's probabilistic risk-bound procedure. Questions from
one scene are correlated. Current finals become known regression assets, never
a reusable blind exam. Generic anatomy cannot fill invisible image parts.

[Label-smoothing research](https://arxiv.org/abs/1906.02629) motivates testing
softer supervision, not assuming it guarantees reliable confidence here.
The input edge view is our own bounded experiment, not reproduction of a
published architecture or proof that image recognition universally needs it.

Backup uses the existing non-forced catalogue branch and a separate Git index.
The user's checkout/index and workbook must match recorded hashes. Evidence
uses <=32MiB parts with per-part and reconstructed-archive SHA256. Concatenate
parts in manifest order, verify the archive, then safely extract; individual
source/data hashes are also recorded.

## Audit correction: historical background shortcut

The 2026-10-10 continuation reproduced a deterministic label/RGB background
confound in native V1-V7. A background-only rule predicts all 10,000 left and
right patterns correctly. Their native high pattern scores are not evidence of
pattern understanding; keep original numbers but do not declare mastery. New
source defaults use domain-separated label RNGs, with an explicit archival-only
compatibility option. Stored original Scene renderings, source capsules and
inherited tensors remain untouched. Fresh independent-label V8 is a new
experiment, not a repair of old finals. Full audit, earliest finishing time and
current job handoffs: `docs/m33_composition_six_hour_work.md`.

# Balanced foreground continuation, 2026-10-10

User authorized diverse-data fine-tuning after the six-hour V18 failure.
This stage does not claim M33 closure or activation of experimental weights.

## Preregistered comparisons (before any training)

V19: balanced native/authored 32/32 minibatches. Within each cohort sample a
task uniformly, an answer uniformly, then a row uniformly. UNKNOWN stays a
supervised answer and is not removed to improve coverage. Increase authored
training from 3,000 to 6,000 scenes; keep 9,000 native and 600 per evaluation
cohort. Both use independent label/style RNG streams, palettes, contour and
aspect variation, paper backgrounds, hidden objects, and similar unsupported
contours/colors. No textbook source crops enter training or calibration.

V20: the exact same frozen generation seed, scene counts, own warm anchor,
schedules, precision, calibration and acceptance criteria, plus 0.1 times
visible-foreground attention KL on authored TRAIN only. Renderer alpha masks
are labels, not model inputs. Hidden targets and native samples have zero
auxiliary supervision. Masks reflect with their images. Only RGB and the RU/EN
query enter inference; model capacity and candidate parameter keys are unchanged.
The two candidates are planned before finals; V20 is not selected or tuned from
V19 final outcomes. Shared final pixels are a paired comparison, not a second
independent blind exam. No claims of causal benefit from comparison against V18
with different seeds and training counts.

Seed 16061; 10,000 steps per joint/curriculum schedule; same V18 own selected
curriculum anchor. Lowest balanced single-view DEV CE only selects each schedule.
Reflection unanimity, JS 0.2, supported-answer smoothing 0.02, IEEE precision,
strict coverage-guarded calibration, and all old acceptance criteria remain.
No confidence threshold retuning after final evaluation.

Both frozen candidates will also receive the same four exposed textbook panels
(V4 mathematics / V3 language / V2 art / V1 mathematics), prepared as current
source-bound v11/v12/v13/v14 directories respectively. No page or failed asset
will be removed after inference. Cold procedural contours use 600 scenes, seed
20061, for both candidates; their families were already inspected in prior
work, so these are paired held-family diagnostics, not independent semantic gold.

## Research rationale and limits

[Group shifts](https://arxiv.org/abs/1911.08731) motivate checking minority
groups separately; this implementation is group-balanced sampling, not Group
DRO and not a generalization guarantee.
[U-Net](https://arxiv.org/abs/1505.04597) motivates explicit foreground
supervision; this small attention KL is not U-Net or a segmentation decoder.
[Outlier Exposure](https://arxiv.org/abs/1812.04606) motivates diverse unsupported
examples; closed-head UNKNOWN examples are not a proof of universal OOD rejection.

## Results

V19 completed authentic remote training and frozen inference/arithmetic replay.
V20 also completed authentic remote training and frozen inference/arithmetic
replay under its preregistered unchanged intervention. Both are rejected.
Permanent dictionary, originals, prior failures and user working-tree changes
remain untouched. Four prior textbook panels, if rechecked, are exposed
regression diagnostics, not independent semantic blind sources.

### Engineering checks before fitting

102 focused unit tests passed. Initial two pipeline checks each exposed the
same outdated archive-count assertion (40 expected, 41 actual when the TRAIN
foreground array is present); the verifier itself replayed inference successfully.
Both failed XML receipts are retained, not replaced. The fixed targeted check
passed 6 tests with 2 deliberately absent-contract skips. The new extra array is
allowed only for exposure TRAIN; forged final masks and altered/resealed training
masks are rejected. Equal inference logits with/without training attention,
unmodified inherited tensors, foreground-only gradients, fair group sampling,
and exact reflection/mask alignment have direct tests.

Original V19 capsule SHA256:
`5a252b40582116c350248a66e4dc3f5444699d3f79b7be9ee16d8bd46adfa6c9`.
Warm anchor SHA256:
`5ea936eb17e0065a60c253d599fe60069596f042e5db5487ac1efb3698cbd724`.
V20 capsule SHA256:
`59c87f06258bbd3b63fb668edf71700c4eccc3cc234b9ad84277061c363f44ff`.
Both capsules' manifests match exactly on all 447 sealed source files; different
archive hashes reflect packaging metadata, not a changed model implementation.
Remote preflight passed 572 tests / 58 inapplicable-contract skips (747.03 s).
Local scoped regression passed 792 / 58 (1371.89 s), plus all 110 supplementary
old object-course/textbook-inventory tests. Combined disjoint collection:
902 passed / 58 skipped. The 58 skips are 26 absent foreground contracts,
9 absent aspect contracts, 10 absent paper contracts, 11 absent strict-calibration
contracts and 2 absent auxiliary contracts. The backup-helper allowlist extension
was separately checked with 16 passing tests, including the final source/document
allowlist additions. The full collection was not rerun after helper-only changes.
V20 remote preflight independently passed 572 / 58 (910.07 s). These timings
are not a speed comparison: its CPU preflight overlapped V19 GPU training.

A read-only comparison with the hash-verified V18 archived control renderer
confirmed exact RGB equality for 100 generated paper scenes. Actual V19 training
gallery was downloaded, independently byte-hashed against the remote original,
and visually inspected (SHA256
`92c6626bf699a0d2ed54a662d80e778489c539cc318bc517ad9bb0baa8ab7e2d`).
Authored known-shape records: 3,692 / 12,000 shape questions; the balanced rule
expects 8.533 known authored-shape samples per full 64-question minibatch,
versus V18's 1.641. This is sampling mass, not measured recognition accuracy.

### Completed V19 (balanced, without foreground KL)

Joint 10,000 steps: best DEV CE 0.0233639078 (step 7,200), 653.70 s total.
Curriculum 10,000 steps: best DEV CE 0.0231850529 (step 10,000), 761.75 s total;
selected checkpoint SHA256
`a5e0b23aa38d44580fad5878fee91f746e065ab418c270860a9eb14d0af48ac8`.
Frozen thresholds: color 0.97, shape 0.90, pattern 0.98, all selected by the
same strict calibration rule. Shape now has eligible calibration coverage;
the threshold was not manually lowered in response to final data.

| V19 assessment | Accepted errors | Correct positive recall | Outcome |
| --- | ---: | ---: | --- |
| Ordinary final | 0 | 93.03% | Overall trial still rejected |
| Held combinations | 0 | 94.07% | Overall trial still rejected |
| Altered-style transfer | 0 | 91.26% | Pattern 78.37%; complete descriptions 74.98%, fail |
| Authored paper final | 63 | 90.56% | Fail |
| Exposed V4 math panel | 0 | 72.14% | Fail |
| Exposed V3 language panel | 0 | 66.67% | Fail |
| Exposed V2 art panel | 0 | 74.50% | Fail |
| Exposed V1 math panels | 7 | 68.18% | Fail |
| Paired cold contour screen | 0 | 93.11% | Fail on a per-family/task gate |

All four source and the cold screen have authentic remote original-inference
and arithmetic replay receipts. Aggregate accuracy cannot override asset/task
failures. The 63 authored errors comprise 61 unsupported turquoise-to-green
color assertions and 2 solid-to-spotted pattern assertions. Exact original
96px error inputs are preserved and visually reviewed, not regenerated. The
7 old mathematics-panel errors are shape errors. This is improved useful
coverage with unsafe residual assertions, not an accepted model or evidence of
photographic/object-name mastery. V19 status: NEEDS_WORK_NOT_PRODUCTION.
No candidate is activated and no catalogue mastery percentage is raised.
The cold failure is specifically chevron-pattern positive recall 62.996%
(143 correct accepted / 227 positives); global task averages are higher and
do not conceal this weak group. The screen has 253 chevron-pattern questions,
including 26 genuine UNKNOWN/hidden cases.

Intermediate code/protocol backup: `ecb15a1d821e76b582bdc33629f9e68d963e0815`.
Completed V19 data/weights/replays backup:
`fb171b9cd5042f0931966da3df4a1466628bd538`. Both used scoped non-forced pushes;
the main HEAD/index/workbook are unchanged. Later V20 work is not yet included
in those completed backup receipts.

### Completed V20 (same data, foreground KL 0.1)

Joint 10,000 steps: best DEV CE 0.0267506251 (step 9,000), 679.26 s total.
Curriculum 10,000 steps: best DEV CE 0.0260769064 (step 9,000), 714.16 s total;
selected checkpoint SHA256
`1b742d02a6dd2736c43b9c07d0ee9dede585c97adc0aa102d3617d445d6644be`.
Frozen thresholds: color 0.97, shape NULL, pattern 0.97. No shape threshold
qualifies under the unchanged calibration constraints; inference therefore
refuses every shape answer. This is not restored shape competence.

| V20 assessment | Accepted errors | Correct positive recall | Outcome |
| --- | ---: | ---: | --- |
| Ordinary final | 0 | 63.49% | Shape coverage zero, fail |
| Held combinations | 0 | 63.03% | Shape coverage zero, fail |
| Altered-style transfer | 0 | 61.11% | Shape coverage zero, fail |
| Authored paper final | 0 | 75.61% | Shape coverage zero, fail |
| Exposed V4 math panel | 0 | 57.14% | Fail |
| Exposed V3 language panel | 0 | 55.56% | Fail |
| Exposed V2 art panel | 0 | 67.33% | Fail |
| Exposed V1 math panels | 0 | 52.05% | Fail |
| Paired cold contour screen | 0 | 80.76% | Shape coverage zero and weak pattern family, fail |

All four source screens and the cold screen have authentic remote receipts
replaying the original frozen candidate and independently recomputing arithmetic.
Chevron-pattern recall is 70.04% (159 / 227), still below its per-family gate.
Complete eligible three-attribute descriptions are zero throughout, because
shape is refused. The reviewed error-preview PNG is correctly empty: there are
zero accepted authored-final errors, not zero recognition errors or refusals.
Before rejection/consensus, single-view authored argmax has 488 wrong assertions;
its 98.74% positive recall does not justify enabling those answers.

### Paired conclusion and handoff

Read-only NPZ comparison confirmed all 40 base arrays byte/value-identical
between V19 and V20. V20 adds only `exposure_foreground`, confined to TRAIN.
Both use 15,000 training scenes (90,000 question records), the same warm anchor
and all 447 matching source files. Both ran joint and curriculum schedules,
40,000 total optimizer steps across the two experiments. Capacity is unchanged:
974,889 frozen inherited parameters and 923,232 trainable parameters. Peak
observed VRAM was 2,964 MiB / 3,370 MiB respectively on the remote notebook.

Balanced V19 restores useful calibrated shape answering compared with V18,
but retains unsafe unsupported-color and pattern assertions. The paired V20
foreground intervention removes observed accepted errors on these panels at
the expense of shape coverage. One seed and one loss coefficient cannot establish
general superiority, and selection must not favor either using final outcomes.
Neither is activated; catalogue statuses/percentages, workbook and PDF originals
remain unchanged. This is color/shape/pattern work, not new animal or object-name
recognition and not strict-U/M33 closure.

Next bounded experiment should diversify unsupported hues near known color
boundaries and separate contour/pattern evidence from foreground localization.
Use a new preregistered seed/policy, TRAIN-only annotations and untouched final
families; do not fit the preserved error inputs or reuse these panels as blind
tests. Review a genuinely separate source-family training/calibration/final split
before admitting real illustrations. Do not expand capacity or lower confidence
merely to hide the measured refusal/error tradeoff.

The final scoped backup receipt is stored under
`D:\ai-brain-data\visual-lexicon\balanced-backup-20261010-v3\push-receipt.json`.
It is authoritative for the final commit; no receipt is claimed until its push
and remote ref are verified. Backup storage is not self-contained: preserve the
D: archive junction, its C: target and the W: main Git object store.

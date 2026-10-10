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

Pending authentic remote training and frozen inference/arithmetic replay.
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
was separately checked with 16 passing tests. No final accuracy claim yet.

A read-only comparison with the hash-verified V18 archived control renderer
confirmed exact RGB equality for 100 generated paper scenes. Actual V19 training
gallery was downloaded, independently byte-hashed against the remote original,
and visually inspected (SHA256
`92c6626bf699a0d2ed54a662d80e778489c539cc318bc517ad9bb0baa8ab7e2d`).
Authored known-shape records: 3,692 / 12,000 shape questions; the balanced rule
expects 8.533 known authored-shape samples per full 64-question minibatch,
versus V18's 1.641. This is sampling mass, not measured recognition accuracy.

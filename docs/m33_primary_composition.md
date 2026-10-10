# Own compositional vision pilot, 2026-10-09

This is a new developmental course, not M33 closure, a general language model,
animal recognition, or a fresh independent photographic examination. No
experimental weights are activated. The permanent catalogue remains authoritative.

## Design and observation boundary

The pilot learns RGB plus bounded Russian/English questions about the **left or
right visible object**, predicting eight colors, four shapes and three surface
patterns. It has one inherited own causal core, frozen old tensors, an appended
word embedding, pixel residual and learned attribute readout. The second version
adds word-to-pixel attention with input-grid coordinates; no renderer boxes,
object attributes, source IDs, labels or scene metadata enter model inference.

Color, shape and pattern are evidence, not a hard identity rule. Animal anatomy
and typical properties must remain separate from particular visible observations.
Not-visible means unknown, not absent. Full occlusion controls do not establish
competence with partial occlusion. Structured descriptions list only accepted
observations; object identity stays UNKNOWN in this course. No species name or
free-form description was learned here.

The catalogue appends 27 explicitly scoped meanings, including patterns,
dark green, visibility, animal parts and fruit parts. Human ears/legs/head retain
their old IDs; animal meanings get separate IDs. Animal and fruit-part meanings
are planned vocabulary, not learned recognition. Ossicones are distinguished from
ears and ordinary horns. Short definitions remain at most 20 words.

## Experiment and results

Each version compares joint training with a curriculum that initially omits
pattern questions. Both schedules reset to the same initialization and own weight
anchor. Winner selection uses class/task-balanced development cross-entropy only.
Calibration is separate. At least 40 accepted calibration answers and zero
observed calibration errors are needed for each task's threshold; otherwise that
task always abstains. Questions from one scene are correlated, not independent
source examples. Risk is empirical, not a promise of never being wrong.

There are 1,200 training scenes and 240 each for development, calibration,
ordinary final, held combinations and altered-style transfer, six questions per
scene. Green oval and blue square pairs are excluded from train/dev/calibration.
All cohorts use the same procedural generator; new seeds are **not** a blind
independent source examination. V1 results informed V2 design. V2 uses new seeds,
and the V1 failure remains unchanged.

| Version | Steps per schedule | Finding |
| --- | ---: | --- |
| V1, shared frozen-core readout | 1,800 | Ordinary raw positive recall 49.5%; no task qualifies for useful safe answering. |
| V2, learned attribute attention | 6,000 | Better ordinary recognition, but incomplete descriptions and unsafe transfer. |

V2 selects the curriculum checkpoint at step 3,300: dev CE 0.084881 versus
0.092830 for joint training. This single comparison does not establish that
curriculum is generally superior. New trainable parameters: 200,432; inherited:
974,889. The inherited tensors remain byte-identical. Delegated old inference is
numerically identical on six examples for each of seven tasks, not a new full
seven-skill acceptance exam.

| V2 cohort | Raw positive recall | Accepted answers | Accepted errors | Safe positive recall |
| --- | ---: | ---: | ---: | ---: |
| Ordinary final | 96.64% | 749 | 0 | 57.26% |
| Held color/shape combinations | 79.66% | 764 | 5 | 58.03% |
| Altered stripes/spots | 82.65% | 665 | 67 | 45.72% |

On ordinary final, safe color recall is 99.54%, pattern recall 72.25%, and shape
recall zero: shape calibration is disabled. Therefore **complete three-attribute
description recall is zero**. The same policy rejects all blank-image inputs in
the ablation. Neither high ordinary raw accuracy nor zero ordinary accepted
errors overrides failures on combinations and altered style. Status:
`NEEDS_WORK_NOT_PRODUCTION`.

Source capsules, checkpoints, exact dataset arrays and per-record probabilities
are kept in `D:\ai-brain-data\visual-lexicon\composition-20261009-v1` and `v2`
(full second name: `composition-20261009-v2`) and on the remote notebook under
`/home/ibicza/ai-brain/runs/m33-composition-20261009-v1` and `v2`.
The catalogue associates 45 full-frame PNG examples with explicit target sides,
split roles, input hashes and procedural provenance. Known final examples are
regression assets now, never a new blind examination. Missing dark-green examples
in the held-pair cohort are not invented: that cohort contains only green/blue.

## Verification and next boundary

### Current audit boundary (2026-10-10)

The V1/V2 results above are historical, not current mastery evidence. The
six-hour continuation found a background/label RNG shortcut in native V1–V7;
their high pattern scores must not be treated as learned pattern recognition.
Original arrays, weights and reports remain unchanged. New experiments separate
label, background, contour, palette and aspect-ratio random streams. Details and
the live handoff are in [the work journal](m33_composition_six_hour_work.md).

Synthetic success alone does not admit textbook or photographic recognition.
Real textbook controls use original-byte/page hashes, preserved raw crops and
independently reconstructed input pixels. Repeated pairs/questions from one
crop are correlated, not additional independent source examples. Annotation is
human-readable but primary-agent manual, not an independent semantic blind exam.
Once evaluated, a source family is exposed; further results are regression
diagnostics. UNKNOWN is scoped to this head's answer vocabulary, not evidence
that other courses forgot their words. No candidate has been activated.

Opt-in `coverage_guarded_strict` calibration keeps the original fixed grid,
zero observed calibration errors and minimum support. It additionally requires
useful positive/unknown recall in each calibration cohort before choosing the
highest eligible threshold. It uses calibration only, after development-only
weight selection. This is an empirical policy, not a statistical guarantee of
zero future errors or an implementation of conformal/SGR risk bounds.

The first actual strict-calibration experiment V18 completed remote training and
frozen inference/arithmetic replay. It is **not accepted**: all fixed-grid shape
thresholds fail authored positive coverage, so that task is entirely refused.
Two accepted pattern mistakes remain on authored final. Four real-source panels
have zero accepted mistakes but inadequate positive/task/asset coverage. The new
V4 page is now exposed; neither its first assessment nor repeated old panels is
an independent semantic blind examination. See the journal's completed-results
table and original receipts. No candidate has been activated.

Historical initial checks comprised 26 focused tests locally/remotely and 227
combined course/catalogue tests locally. The latest six-hour patch has **832
passed, 32 explicitly inapplicable-contract skips**, zero failures/errors.
Model/training definitions did not change afterward. A final backup-document
allowlist repair was checked separately with 16 passing backup tests; the full
suite was not rerun after that helper-only repair. A separate arithmetic implementation
replays the selected model on calibration and all reported cohorts, independently
recomputes decisions, recalls, false assertions and complete-description rates,
and checks source/data/checkpoint hashes. This is independent calculation, not
independent semantic annotation. The current candidate is rejected for production.

Next: investigate foreground/paper separation and the underrepresented authored
known-shape training group. Distinguish actual wrong/disagreeing views from
correct low-score predictions; changing confidence alone cannot fix the former.
Compare one preregistered intervention at a time, then freeze before new
evaluation. Retain explicit target-binding, UNKNOWN and old-skill
checks. Only then admit reviewed real object/part annotations, including varied
watermelons and giraffes, with per-part visibility and separate author/source
families. Do not fill hidden anatomy from the object name or teach identities
solely through an attribute checklist.

## Research basis and adaptation limits

- [Concept Bottleneck Models](https://proceedings.mlr.press/v119/koh20a.html):
  interpretable intermediate concepts; not proof that our implementation works.
- [Neuro-Symbolic Concept Learner](https://arxiv.org/abs/1904.12584): joint visual
  concepts and grounded language with curriculum. We do not reproduce its full
  architecture or claim the same transfer capability.
- [ARO / compositional VLM limitations](https://arxiv.org/abs/2210.01936): explicit
  object-attribute binding needs its own evaluation.
- [Giraffe Conservation Foundation](https://giraffeconservation.org/facts-about-giraffe/do-all-giraffe-have-horns/):
  ossicone terminology. Generic anatomy is not per-image gold.

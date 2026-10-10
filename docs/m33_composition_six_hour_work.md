# Six-hour own-weight vision continuation, 2026-10-10

User-authorized window: 2026-10-09 23:11:22 UTC through at least
2026-10-10 05:11:22 UTC (02:11:22–08:11:22 Europe/Minsk).
Do not declare completion before the latter time. The goal is active.

Starting evidence is V5, not production: one held-pair shape error and five
style-transfer pattern errors. Old failures and source capsules are immutable.
The canonical workbook and user's Git index must not be overwritten.

## Preregistered next experiment

V6 starts from V5's own curriculum checkpoint, with frozen inherited tensors.
Train on fresh seed 11036, 9,000 scenes and 600 scenes per held-out cohort.
Use the corrected future geometry bounds, spatial readout, shape edges,
0.02 masked smoothing, two schedules selected only by balanced dev loss.
No held color-shape pair or final answer enters training or checkpoint selection.

Test label-preserving vertical/horizontal reflection during training. Horizontal
reflection swaps only the left/right words in the input query. At inference,
compare original, vertical, horizontal and both reflections; remap the query
for horizontal views. Accept a non-UNKNOWN answer only if all four views agree,
using the minimum confidence of those views. Disagreement means UNKNOWN.
This is a conservative agreement score, not a calibrated class probability.
Store unmodified single-view predictions separately for honest accuracy review.
Calibrate the same fixed grid only on calibration, never on known V5 finals.

All existing acceptance criteria remain unchanged: zero accepted errors on all
three fresh final cohorts, >=80% per-task positive recall, >=90% unknown recall,
>=80% complete descriptions and opposite-target binding, no accepted blank.
Passing this bounded screen is not production admission or real-image transfer.

## Research rationale and limitations

[AugMix](https://arxiv.org/abs/1912.02781) motivates semantic-preserving diversity
and prediction consistency. Our bounded reflections are not AugMix's stochastic
mixtures or a reproduction of its experiments.
[M/V-ATTA](https://arxiv.org/abs/2304.05104) studies inference-time views and
uncertainty calibration; our unanimity/minimum rule is a different experiment.
No paper guarantees absence of future confident errors or photographic transfer.

After a successful fresh screen, audit source/split/inference correspondence,
repeat with new unseen seeds and examine an independent rendering/source family.
Then move to the next image block with visible-attribute labels, provenance,
family-separated splits and explicit unknowns. Do not fill hidden anatomy.

## Checkpoints

- 23:16 UTC: verified available remote GPU and disk, read current V5 evidence.
- Structural navigation: graph refresh requested; untracked course absent from
  graph, therefore source and tests are the authoritative verification path.
- 23:21 UTC: 74 focused local tests pass, lint clean. V6 remote continuation
  launched in `/home/ibicza/ai-brain/runs/m33-composition-20261010-v6`, local
  evidence `D:/ai-brain-data/visual-lexicon/composition-20261010-v6`.
  Foreground orchestration session 83066; do not start duplicate training.
- Temporary thread heartbeat automation ID `m33`, every 30 minutes, preserves
  this deadline and must be disabled after the final checked handoff.
- 23:27 UTC: future split audit now checks seed and scene-identity leakage even
  when rendering changes pixel hashes. V6 frozen source is unchanged; later
  experiments receive the guard. 54 focused course/view/comparison tests pass;
  29 pipeline checks also pass after hostile single-view/policy modifications.
- Authored control family prepared, six tests pass: absent targets and contours
  outside the composition head's four-shape scope. Exposure families are triangle
  and cross; held controls are star, pentagon and trapezoid. Exposure never uses
  held color-shape pairs. This shares Pillow, so it is a separate generator, not
  an independent raster engine or photographic/blind annotation exercise.
  UNKNOWN on a star here does not imply that the legacy shape course lacks stars.
- Next operation after V6 completes: run `m33_composition_control_remote.py`
  against its frozen candidate/policy, count 600, seed 2110360000, no calibration
  or training. Store source/evidence in the new child `control-screen-v1` only.

## V6 outcome and preregistered V7 response

V6 is complete and independently replayed, candidate
`b041fd887b5a8b87b19ea4e2cf1ed785b39920163d0cd0c4cc04605f2a49541a`,
source `20041279dad1fb2afb8e4c5c86deacac887702da8b42a5ffc46dc0c31a258f06`.
Joint step 9,000 wins by single-view dev CE 0.0170559. All thresholds remain 0.9.
Ordinary/held-pair accepted errors: 0/0, complete descriptions 98.63%/98.63%.
Transfer: one accepted pattern error, complete descriptions 92.03%; still fails.
Known error `transfer/407`, right pattern: wavy stripes predicted spots, score
0.906542. It is now a regression example, not a future blind question.

Fixed-policy authored controls expose major shift failure, not just one rare
mistake: 1,290 accepted errors / 3,600 questions, positive recall 32.06%.
Color 527, shape 111, pattern 652 accepted errors; color unknown recall zero.
Visual QA of the contact sheet confirms authored contours/solid colors/marks,
but is not a full independent per-image semantic annotation. Never hide this
failure or claim real-source mastery from the earlier course.

V7 will keep V6 as its own warm start and all old evidence immutable. New seed
11037, 9,000 native training scenes, 1,800 auxiliary exposure scenes. Mix 48 native
and 16 exposure questions per batch. Exposure has triangle/cross and native
shapes, pastel backgrounds, absent targets; excludes all held color-shape pairs
and star/pentagon/trapezoid contours. Add a separate fresh exposure calibration
cohort; never calibrate on held controls. Keep the original native final cohorts
and add a fresh held-control final cohort with the same zero-error and useful
recall requirements. Reuse neither V6 final seeds nor control seeds.

Compare the same two schedules, preserving single-view balanced native dev CE
selection. Test a bounded two-reflection Jensen-Shannon consistency penalty
0.2 in addition to 0.02 supported-class smoothing. This is not full AugMix.
Keep the four-view conservative inference policy; do not increase thresholds
after inspecting any final. Shared inherited tensors remain frozen.

Full local regression at this boundary: 433 passed, two skipped. Workbook,
main HEAD and index hashes match the pre-existing user state. No temporary test
directory was deleted; the D free-space display was inspected and shows ~1.97GiB.

Continuation handoff at 23:36 UTC (not completion; earliest finish 05:11:22 UTC):
no training jobs remain running. V6 session 83066 and control session 38732
finished successfully as executions, with FAILED model gates preserved above.
Control source capsule is
`13245d159dbc190a4aee41c5f738bff9675cfb61c50b252ad03bd22c40bdd24a`.
Current next action is implement and test V7 exposure/calibration/control-final
integration and consistency loss, then seal and launch on the notebook. Avoid
duplicating the completed V6 or its `control-screen-v1` child. Neither the active
goal nor temporary `m33` heartbeat should be completed/disabled before the window.

The positive captions in this experiment mean only geometric attributes.
Authored shape UNKNOWN is a head-capability boundary, not a claim that a child
cannot name stars or that our legacy six-shape model never learned them. Future
expansion must retain/delegate those old skills; this test must not erase them.

V7 preregistration refinement before sealing/training: add a separate authored
development cohort at seed offset 90,000. Select by equal-weight native and
authored balanced dev CE, rather than native-only CE, so early checkpoints
cannot win while ignoring the newly exposed failure. Calibration remains separate
at offset 70,000; held contours at 80,000. No final is used for this refinement.

23:43 UTC execution checkpoint: V7 integration is implemented; 61 focused
pipeline/control/view tests pass against the final 10-cohort implementation,
including independent calibration/final replay and masked-JS finite gradients.
V7 remote orchestration is running in session **28348**, local root
`D:/ai-brain-data/visual-lexicon/composition-20261010-v7`, remote root
`/home/ibicza/ai-brain/runs/m33-composition-20261010-v7`. Do not start a duplicate.
It must finish pre-training tests before data/training. Source capsule and own
warm checkpoint are transported with independent byte-hash checks. Graph rebuild
session 73079 is running locally. Earlier test sessions are all finished.

Same-pixel frozen V5-policy comparison on V6 arrays is now preserved at
`composition-20261010-v6/same-pixel-comparison.json`: ordinary errors V5/V6 1/0,
held pairs 0/0, transfer 0/1. Transfer positive recall V5/V6 98.08%/97.28%.
Thus reflections and extra training are **not established as a monotonic gain**;
do not compare the six V5 errors on its different original pixels against V6's
one error as if that proved a causal improvement.

V6 result/replay/control summaries are copied into the permanent catalogue
directory as versioned JSON, without editing XLSX rows. New V6/V7 evidence has
not yet been added to Git backup; batch it after the next audited boundary using
the isolated backup index/branch. Preserve original main HEAD/index and workbook.
Monitor D space (~1.95GiB) and avoid redundant large bundles per iteration.

V7 sealed source SHA256:
`30eb69ae818a226e30a6249cbe1a5a4c218fcaecb098d50e85b57082b0e4d6b0`.
Graph rebuild 73079 finished successfully; graph still does not index these
untracked course files, and source/tests remain the authoritative evidence.
Checkpoint handoff is a continuation boundary, **not task completion**. The
six-hour goal stays active; next turn must resume session 28348 and act on its
actual results. The `m33` heartbeat provides additional scheduled continuation.

23:54 UTC critical audit: native V1 through sealed V7 have a deterministic
background/label confound. `scenes` and `render_diverse` start the same NumPy RNG
stream from scene.seed. Bits that select patterns are reused in the first two
background uniform draws. On 10,000 fresh scenes at seed 55,150,000,
`floor((background_R - 100) / 80 * 3)` recovers all 10,000 left patterns and the
same expression with background_G recovers all 10,000 right patterns. Confusion
diagonals left [3396, 3307, 3297], right [3352, 3353, 3295], off-diagonals zero.
Previous high native pattern scores are not evidence of pattern understanding.
Preserve historical sources/results; attach this limitation rather than rewrite
them. V7 is already sealed/running; its auxiliary learning may be useful, but
native numeric acceptance cannot repair a confounded experiment. Future cohorts
require independent RNG domains and a tested background-only leakage audit.

Paired V6 known-dev background probe completed at
`composition-20261010-v6/background-probe-v1`: 120 scenes, 720 questions; foreground
geometry/paint RNG preserved, background replaced. Original: 0 accepted errors,
positive recall 99.08%; dark: 11 errors, recall 33.03%; light: 181 errors, recall
43.12%. This is diagnostic counterfactual evidence, not a new blind final.
Probe source SHA256
`2d101d511af8036c061677bea7961a135006aed27cab7813754abdb0ea2576a3`;
independent replay completed.
Follow-up audit found a related confound in primary-zero's textured transfer
noise: first background noise samples predict count and shape with 86.18% and
86.37% accuracy (5,716 normal scenes; shape excludes empty scenes). Ordinary
training backgrounds are fixed, so this does NOT prove historical models learned
this shortcut. Future zero/relations label/geometry RNGs are now separated from
the renderer; archived Scene pixels and own inherited weights are unchanged.
The fixed audit gives 15.83% and 16.64%, near six-way chance. Relations receives
the same source-level protection without claiming a reproduced relation error.
Persistent full receipt: `D:/ai-brain-data/visual-lexicon/rng-shortcut-audit-20261010-v2.json`.

First independent-label focused regression: 110 passed in 145.90s. This preceded
the additional zero/relations generator protections; run broader regression
before freezing the next source. Native pipeline verifies domain policy, reruns
the background detector and regenerates every stored scene under the new label
stream. Hostile leakage-audit edits are rejected before inference replay.

V8 preregistration: warm start the own V7 dev-selected candidate after its sealed
run finishes, but retain its confounded gate limitation. Seed 11038; same 9,000
native / 1,800 authored training scenes and 600 per held cohort; two 9,000-step
schedules, reflections, spatial/shape-edge readouts, smoothing 0.02, JS 0.2.
Only label RNG generation changes for this iteration; keep renderer distribution
and all acceptance/selection/calibration boundaries. No final-derived threshold
changes. The new native and authored cohorts use independent label streams.
If V8 still fails, inspect development evidence and expand background coverage
in a separately frozen later iteration, not by rewriting the V8 final.

Literature checked: background shortcuts are documented in Luo et al.
https://arxiv.org/abs/2107.07746 ; uncertainty/calibration can fail under dataset
shift in Ovadia et al. https://arxiv.org/abs/1906.02530 . Our intervention is RNG
domain separation plus counterfactual audits, not a reproduction of COSOC.
Reflection JS training is a bounded adaptation inspired by AugMix
https://arxiv.org/abs/1912.02781 , not the full AugMix image-mixture algorithm.

00:04 UTC verification boundary: broader course/catalogue regression passed
459 tests, two skipped, in 163.31 seconds. Receipt
`D:/ai-brain-data/visual-lexicon/qa-sixhour-rng-full-tests.xml`.
Ruff passes. Main HEAD/index and XLSX SHA256 still match the recorded user state.
Graph rebuild 52221 completed; untracked course code remains unindexed, not
unreferenced. V7 session 28348 finished both schedules and is now evaluating its
frozen candidate; wait for its hash-checked download before starting V8.

Backup helper `m33_composition_sixhour_backup.py` passes six chunk-integrity and
unsafe-limit tests. It preserves original evidence files directly in Git;
>32MiB files use ordered, hash-checked parts instead of an extra aggregate tar.
Only explicitly scoped completed runs are eligible; main HEAD/index/workbook
are checked before/after, existing backup ref uses compare-and-swap and no force.
Next source/evidence backup will use expected parent
`6a85ac4c2ee087c559809ffc12adedf247905962` and a fresh scoped output directory.
Future transport hashes downloaded local bytes against the original remote
file's SHA256 computed remotely, avoiding a second slow whole-dataset SFTP read.
V7 keeps its original transport unchanged; its current download must finish.
These are storage/transport changes, not changes to model inference or scores.

00:08 UTC: scoped V6/full source audit backup pushed and independently confirmed
at `368f086e6dd6014897f251a7d9350286f487ce2a` (83 changed paths). Receipt:
`D:/ai-brain-data/visual-lexicon/sixhour-backup-20261010-v1/push-receipt.json`.
No main checkout/index/workbook modification; no original evidence deleted.

V7 remote inference/arithmetic replay is complete, model FAILED: native final /
held-pair / transfer accepted errors 0/0/0, authored held-control errors 16;
authored safe positive recall 97.29%, unknown recall 98.43%. Native pattern scores
still carry the separate RNG confound limitation. Selected curriculum candidate
SHA256 `03d4394b9b24cbab57aa10f3c23f092695561166c4f0443fed49d5071ed3f938`;
dataset SHA256 `d7424c17a2423a80ce80bf0838e84b348c65ecfe57d4572eeb10be3040e8fbff`.
V7 slow original transport is serially re-reading the large dataset for SHA;
keep session 28348 alive to preserve its completed download receipt. Remote GPU
is idle (2MiB memory), so this is not an active training job. A separate fresh
SCP bridge checkpoint `composition-20261010-v7/frozen-selected-bridge.pt` was
downloaded and its bytes match the exact independently replayed candidate above.
V8 may therefore start from these verified own weights without waiting for the
old redundant dataset transfer, and without duplicating any V7 GPU job.

V8 started in orchestration session **83663** at 00:09 UTC, local root
`D:/ai-brain-data/visual-lexicon/composition-20261010-v8`, remote
`/home/ibicza/ai-brain/runs/m33-composition-20261010-v8`.
Sealed source SHA256
`47263c78e833bc81b73d44cd373ab4be6a4ac15b573e1b1cb99c4418fb597bc6`.
Exact new transport copied as `transport-executed.py`. Pre-training tests run
before generation or GPU training. Do not duplicate this run. Old V7 session
28348 continues only its original slow evidence download/hash checks. Local
V7 dataset hash is independently confirmed equal to the remote verifier digest.
All 16 V7 authored accepted errors are shape assertions; color/pattern errors
are zero. A supplementary `scientific-validity-notice.json` records native RNG
confounding without altering the sealed model/source/numerical results.
Next actions: finish V7 transfer, inspect V8 data audit/test progress, and analyse
development-only OOD shape evidence for a later iteration. No production weights
or workbook mastery percentages are activated/updated. Roughly five hours remain
before the user-approved earliest finish; goal and heartbeat stay ACTIVE.

Literature follow-up for future OOD shape work: Outlier Exposure
https://arxiv.org/html/1812.04606v3 (discussion sections) finds auxiliary diversity
and closeness of low-level statistics important, not just sample count; Gaussian
noise or easy synthetic anomalies may teach unintended cues. Its multiclass OOD
detector outperforms its tested explicit reject-class option. Our current UNKNOWN
head is therefore not automatically the best novelty detector, and training only
triangle/cross cannot establish broad unseen-shape safety. Future alternatives
may test richer disjoint exposure shapes or a dev-selected own-weight ensemble;
never add star/pentagon/trapezoid finals to exposure and call them blind again.
OpenMax primary abstract https://arxiv.org/abs/1511.06233 motivates feature-space
open-set rejection rather than softmax threshold alone; its full algorithm has
not been reproduced here. CVF HTML was unavailable (403), so do not claim it read.
NumPy official RNG stream guidance was checked at
https://numpy.org/doc/stable/reference/random/parallel.html ; our label domains
use deterministic SeedSequence input lists, not resetting the rendering stream.

00:12 UTC continuation boundary (not completion): V8 session 83663 is running its
remote pre-training pytest, confirmed by live process PID 310394. V7 28348 is
still verifying/downloading original evidence, not using GPU. Resume these two
specific sessions; do not launch duplicate training or repeat V6 backup. Latest
backup parent is 368f086e6dd6014897f251a7d9350286f487ce2a. Both canonical XLSX
and main Git HEAD/index remain unchanged. Earliest finish is still 05:11:22 UTC.

00:14 UTC V8 terminal preflight failure: session 83663 ended with one missing
script-import test (217 passed, 1 failed); no training was started. Source capsule
is preserved unchanged. Retrieved original XML SHA256
`8125ffc6c820a62cd2ea75ecf81c4460a848b7f8c977a5c9715f4b6c03fe5f44`;
failure receipt `composition-20261010-v8/remote-preflight-failure.json`.
Missing relations pilot transitively imports zero pilot. Packaging now includes
these dependencies by AST import closure, and includes its own packaging module
for an isolated-capsule test. That test imports legacy pilots from an extracted
capsule, with no checkout scripts on PYTHONPATH. Ten focused capsule/backup/policy
tests pass locally; new driver preserves failed preflight XML automatically.
V9 is the replacement independent-label training iteration: exact same V8
preregistration/settings/seed 11038 and verified V7 warm checkpoint, since V8
never accessed training/final data. Fresh local/remote v9 paths/capsule required;
do not overwrite or pretend V8 passed. Source/tests change only packaging here.

Replacement V9 started in session **5408**, local
`D:/ai-brain-data/visual-lexicon/composition-20261010-v9`, remote
`/home/ibicza/ai-brain/runs/m33-composition-20261010-v9`.
Sealed source SHA256
`65e977f97004c3470e876fadeafa238de11ae86f0140bf88a3e3b1b1d409e80d`.
Exact driver copied as transport-executed.py. V7 session 28348 has now completed
its original download/hash checks, receipt REMOTE_CONTINUATION_REPLAYED,
elapsed 1845.34 seconds; it is no longer live. V8 83663 is terminal failed before
training. Only V9 5408 is active; never restart V7/V8. Next backup parent remains
368f086e6dd6014897f251a7d9350286f487ce2a; include completed V7 and preserved V8
preflight failure, not a duplicate V6 bundle.

V9 remote preflight passed 221 tests in 133.01s; the isolated-capsule test is
included. V7 known-final shape failure breakdown is pentagon 10 / trapezoid 6;
max accepted error score 0.956791. These are now diagnostic known examples, not
fresh blind tests. Do not fix their original thresholds and claim success.
The next safe study can compare dev-only own joint/curriculum model agreement
or expand disjoint auxiliary shape diversity, guided by OOD literature. It must
preserve held star/pentagon/trapezoid from exposure and use a new frozen final.
Next backup includes completed V7 and the preserved untrained V8 preflight fail.

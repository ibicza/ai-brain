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

00:29 UTC: that backup finished and remote push is confirmed at
`93956e9137781e179c0828cc1205035f6ef97411` (52 changed paths), receipt in
`sixhour-backup-20261010-v2/push-receipt.json`. No files deleted.
V7 development agreement study V1 on CPU failed its strict CUDA-history CE
tolerance: joint CE 0.01948072 versus original 0.01950666. Failure and partial
scores preserved; no acceptance claimed. The prototype also lacked a start-time
script snapshot; later studies pin/hash their script before imports and reject
script drift. New helper's seven pure fusion validation tests pass.
V7 development agreement V2 on the original GPU successfully reproduced both
original dev scores exactly: joint 0.01950665656477213, curriculum
0.018920577131211758. Pinned script SHA256
`bdf7d9d886662584b4586de4fc169cba6fa141b38f13e6f7514a1c3cbdbc0718`;
known dev/control-dev only, no training/calibration/final access. Both candidates
and their unanimity have zero accepted errors on these easy development sets,
so this study does not establish an ensemble advantage on unfamiliar contours.
Original model/source/checkpoint/data hashes remain unchanged. CPU/GPU difference
cause is not yet proven; official PyTorch 2.9 notes document separate cuDNN TF32
control and rounding effects: https://docs.pytorch.org/docs/2.9/notes/cuda.html .
Future protocols should record numeric backend settings and test portability,
not silently loosen numerical tolerances or rewrite historical GPU results.

00:40 UTC: V9 session 5408 completed with independent inference/arithmetic replay
and SHA-checked local evidence. First clean, domain-separated native run has
zero accepted errors on ordinary, held-pair and transfer finals, with positive
recall 99.76% / 99.60% / 97.86%. Authored held controls still have seven accepted
errors, all unsupported shape assertions; overall safe positive recall 98.64%.
Result remains NEEDS_WORK_NOT_PRODUCTION. Own selected curriculum checkpoint
SHA256 `2c306583a9df3b5b549f0e2ba4660ca46c4f64c5d08bcad2b6ec882568344385`.
The V7-to-V9 numerical difference is not a controlled causal comparison: seeds
and native label-generation policy changed. It does not prove a seven-versus-
sixteen error improvement on the same test. Native clean result is evidence
against needing the discovered background shortcut, not a general vision proof.

Next preregistration, V10 (before generation/training): keep own inherited core,
verified V9 warm candidate, 9,000 native and 1,800 authored training images,
600 images per held/dev/calibration cohort, seed 11039, 9,000 steps per schedule,
four-view unanimity/JS 0.2, shape edges, smoothing 0.02 and original acceptance
criteria. Change only the authored exposure profile from triangle/cross to those
plus hexagon/heart/arrow/crescent. These are offline unsupported-contour examples,
not new lexical shape classes. Original supported four-shape scope stays intact.
Star/pentagon/trapezoid remain wholly excluded from training, development and
calibration. New final pixels/seeds are held out, but these contour families are
already known from earlier examinations: do not call this an unfamiliar-family
blind external-source exam. Existing standard/archival profile remains default
and its labels/rendering unchanged. Frozen V9 capsule is not modified.
The new exposure profile is recorded before training, independently regenerated
and family-audited by the verifier; source tests include opt-in replay, hidden
targets, bounded contour pixels, wrong-profile and held-family rejection.
This adapts the diversity lesson from Outlier Exposure, not its full uniform-
posterior objective: https://arxiv.org/html/1812.04606v3 . The paper also warns
against easy synthetic anomaly cues, so passing these contours alone is not
enough to graduate to unrestricted photographs or textbook pages.

00:42 UTC: V10 started in orchestration session **52843**, local
`D:/ai-brain-data/visual-lexicon/composition-20261010-v10`, remote
`/home/ibicza/ai-brain/runs/m33-composition-20261010-v10`. Sealed capsule SHA256
`45a5da4cb0edceddfdf7181406d80f28f919d102f0fea64716a027f95a5ef16d`.
Transport input is pinned at `D:/ai-brain-data/visual-lexicon/transport-v10-input.py`
and start-time copy `v10/transport-executed.py`. An initial invocation without
scripts on PYTHONPATH failed at import before making a run directory; the same
fresh run was then launched with explicit src/scripts PYTHONPATH. No duplicate
training. V9 session 5408 is finished; do not restart it. Local new-contour /
tiny train-freeze-replay tests: 78 passed in 212.95s; backup/capsule/dev diagnostic
tests: 23 passed in 4.33s (separate suites, not one claimed full regression).

Pinned V7 numeric intervention `numeric-backend-v1` completed on the notebook,
script SHA256 `e9496434e2571d7639fff2b10b8bf7fdb0fdc61f52000fd3f4e6f09d44814dce`.
Same original capsule, joint checkpoint, batch size and dev/control-dev inputs:
CPU CE 0.019480719231069088; CUDA TF32 convolution reproduces historical CE
exactly 0.01950665656477213; CUDA IEEE convolution gives 0.019480731338262558.
Authored max score distance to CPU falls from 0.0328304 to 0.0000027418, raw
argmax disagreements from one to zero. This controlled intervention identifies
cuDNN TF32 as the material source of this specific prior CPU/GPU discrepancy.
It is not a universal bit-equality proof; the old failed CPU study remains failed.
Only new runs may preregister an explicit IEEE backend; V10 original capsule/
default training backend stay unchanged. No training or final access in study.

00:50 UTC: V10 remote capsule preflight passed 244 tests in 193.67s and is now
training (joint step 3000 observed). Same source capsule remains unchanged.
Local development for a FUTURE image block now adds an opt-in background_clear
profile: independent gray brightness 60..205 plus per-channel jitter -6..6 using
its own SeedSequence domain M3BL. No label-conditioned background/contrast choice;
old geometry RNG draws and all standard/default pixels stay unchanged. Transfer
still reserves waves/irregular spots; the broader background is not a new animal
or word class. Statistical shortcut audit now samples each selected actual
renderer family, including legacy's integer background, rather than assuming
every renderer uses the same floating RGB draw. Source-level stream separation
plus that specific detector still does not prove absence of every shortcut.
Eighty focused source/geometry tests passed before adding one extra direct-call
archival renderer test and the sixth end-to-end wide-profile fixture.

Numeric backend contract is opt-in for future runs, with IEEE settings separately
fixed for global/CUDA matmul/cuDNN/conv/RNN using PyTorch >=2.9 API. New protocols
record exact precision settings and backend versions; new verifier reapplies the
declared precision and rejects result/protocol drift, without pretending runtime
version metadata guarantees all-device bit equality. Archived capsules do not
receive a backfilled contract. Neither future feature is in the active V10 run.

Fresh combined course/catalogue regression is running in session **55521**,
receipt `D:/ai-brain-data/visual-lexicon/qa-sixhour-wide-full-regression-v1.xml`.
It includes six tiny train/freeze/replay fixtures (the sixth is wide background
plus IEEE), all primary course tests and lexicon tests. Do not claim it passed
until completion. Earlier numeric-only suite session **24269** is still running
its already-loaded five fixtures; it predates the latest background integration.
Resume exact handles, not duplicate test/training jobs. Goal/heartbeat ACTIVE;
earliest finish remains 05:11:22 UTC. Backup parent stays 93956e9137781e179c0828cc1205035f6ef97411
until a new scoped push receipt confirms otherwise.

00:50 UTC: numeric-contract suite 24269 completed: 94 passed, two skipped in
275.71s. Both skips are the deliberately inapplicable exposure-family tamper
test on fixtures with no auxiliary cohorts. It is no longer live. Combined
latest-source regression 55521 and V10 training 52843 remain live.

00:54 UTC: scoped V3 backup pushed and independently confirmed at
`81f1cd6ff241370f2f0136c16fc891f5c8e96cfb` (126 changed paths), including complete
V9 evidence, original V7 dev studies and the CPU failure, numeric intervention,
new source and completed test receipts. Its predecessor was 93956e9...; every
next backup must use the full NEW expected parent above. Main HEAD/index and
canonical workbook hashes remain unchanged; no original files deleted. Current
free space about D 1.06GiB, W 0.429GiB, notebook 9.5GiB: avoid unnecessary copied
aggregate archives and duplicated old datasets in later backups.

Primary literature follow-up: Concept Bottleneck Models
https://proceedings.mlr.press/v119/koh20a.html and NS-CL
https://arxiv.org/abs/1904.12584 motivate supervised/grounded attributes and
compositional language, but our RGB residual model is NOT a strict concept-only
bottleneck or NS-CL reproduction. Energy-based OOD Detection original algorithm
https://arxiv.org/html/2010.03759v3 (sections 2, 3.1, 3.2) uses raw logit
logsumexp and optional energy-gap loss to address softmax overconfidence. If
diverse exposure still leaves accepted shape mistakes, a future KNOWN-DEV-only
study can compare raw-logit energy and softmax novelty ranking before any fresh
policy/training iteration. Do not reconstruct logit energy from normalized
probabilities: their common logit offset has been lost. UNKNOWN-head energy and
task-conditioned supported-class energy are different objectives; do not assume
the paper transfers without validation. No energy policy is implemented yet.

00:55 UTC handoff for automatic continuation (NOT task completion): only V10
training/orchestration **52843** and combined latest-source regression **55521**
are live. V10 joint 9000 done, curriculum step 600 observed. V7/V9 studies,
numeric suite 24269, backup 83084, and graph 39515 are finished; do not restart.
Next: inspect 55521 outcome; refresh 52843 and original capsule/receipts; diagnose
actual held errors without changing old results; then preregister a fresh wide-
background/IEEE image block (likely V11 seed 11040) if checks justify it. Preserve
known versus blind family distinction and dev-only model selection. Still over
four hours before earliest finish 05:11:22 UTC / 08:11:22 Minsk; goal and temporary
heartbeat stay ACTIVE, not paused/complete. If current block passes before then,
audit it and proceed to the next image block rather than stopping early.

00:56 UTC: combined latest-source regression **55521 completed**: 562 passed,
four skipped in 387.16s. It is no longer live. Receipt is
`qa-sixhour-wide-full-regression-v1.xml`; this latest receipt was generated AFTER
V3 backup and must be included in a future scoped backup. All six pipeline
fixtures, including wide backgrounds/IEEE, completed. Only V10 **52843** remains
live, curriculum step 1200. This is a tested source boundary, not a claim that
the still-training V10 model passed its final screen.

00:59 UTC: four full-suite skips were inspected individually: two deliberately
inapplicable exposure-family checks without auxiliary cohorts, and two PDF
extraction tests missing pdfplumber. The bundled runtime has PDF libraries but
not pytest; the project venv lacked pdfplumber/pypdfium2/reportlab. Added only the
three exact bundled versions to a separate optional
`scripts/requirements-primary-materials.txt`; uv dry-run confirmed additive-only
installation (also charset-normalizer/pdfminer-six), no Torch/Pillow/pypdf
replacement. Actual venv remains torch 2.9.0+cu129, Pillow 12.3.0, pypdf 6.19.0.
Dedicated PDF extraction/integrity suite then passed all nine tests in 1.39s:
`qa-sixhour-pdf-extraction-v1.xml`. Its fresh fixture root
`D:/ai-brain-data/visual-lexicon/pdf-extraction-qa-20261010-v1` is now preserved;
NEVER rerun pytest --basetemp against that existing evidence directory.
Skill pdf used for extraction/visual validation only; no textbook or workbook
edited, no final authored PDF deliverable. Latest full suite remains its original
562/4 result; separate rerun resolves the dependency skips, not retroactive edit.
Next backup must include this XML and optional requirements, and future full
runs can now execute those PDF tests. Only V10 52843 remains live, curriculum4200.

PDF fixture visual review also completed on actual saved contact-sheet/page/crop
JPEGs: source text and red illustration retained, full MediaBox preview and its
red crop align, override does not clip the object. These are internal synthetic
QA fixtures, not a new or edited user PDF and not a textbook-training result.

01:00 UTC continuation boundary: post-PDF-dependency combined regression is
running in **70527**, target receipt `qa-sixhour-wide-full-regression-v2.xml`.
Do not duplicate it or reuse the preserved explicit PDF basetemp directory.
Previous regression 55521 is finished (562/4); dedicated PDF rerun 9/0 finished.
V10 **52843** remains the ONLY live model run, curriculum4800 observed. Next
backup expected parent is 81f1cd6ff241370f2f0136c16fc891f5c8e96cfb, not 93956e9.
New full receipts/PDF XML/requirements and this updated worklog are NOT yet in
that V3 commit. D free 1.059GiB, W free 0.404GiB; no deletion authorized by this
iteration, so reduce duplicated backup copies if nearing capacity. Continue
model work/checks for at least four more hours until 05:11:22 UTC; no completion.

01:11 UTC: V10 52843 completed; source capsule
45a5da4cb0edceddfdf7181406d80f28f919d102f0fea64716a027f95a5ef16d,
winning own curriculum8400 candidate
576eed15bc3e600abe52f98c3e26871fc51f0074630ea593d19c22d07824de8d.
Independent replay and transport receipt completed. Native ordinary/held-pair
and authored control_final have zero accepted errors, but native transfer has
one: index2075, transfer/345 right pattern, striped -> spotted, score0.9493251.
Viewed exact preserved RGB (known-transfer-error-2075.png, raw RGB SHA
45a1e56660d6c3382ff814641b0c9a216dffea89679bc0f742fc17c78c250980):
clearly connected wavy stripes. This is a real failure, not relabeled gold.
V10 is NOT admitted. Post-PDF full regression70527 completed564passed/2deliberate
inapplicable skips in381.54s. No live jobs remain at this boundary.

V11 preregistration BEFORE generation/training: seed11040, V10 own warm weights
above, unchanged frozen inherited core,9000 native+1800 authored training images,
600 each held cohort, two9000step candidates, raw balanced dev CE selection,
four-view unanimity/JS0.2, spatial edges, smoothing0.02, diverse foreign contours.
New native curve_background_clear uses independent broad gray backgrounds plus
quadratic/parabolic stripes on two thirds of training-style scenes; sinusoidal
stripes and irregular spots remain transfer-only. Numeric IEEE policy explicitly
frozen for the new run, never backfilled into V10. This jointly changes several
components; cannot attribute any improvement to one component alone. Acceptance
unchanged (zero accepted errors on every cohort/task, recall and binding gates).
AugMix primary abstract (https://arxiv.org/abs/1912.02781) confirms robustness
benefits from training data processing under shift, but this custom curriculum
is NOT an AugMix reproduction or a guarantee against unseen mistakes.

01:17 UTC: V11 transport **38133** launched, local
composition-20261010-v11, remote m33-composition-20261010-v11.
Pinned driver D:/ai-brain-data/visual-lexicon/transport-v11-input.py SHA
2281f2678dd657d5ed2ec5cf6e03fc099a0ebec9020fb274c99dc9d9bc37a294;
original V11 source capsule SHA
6f3fb848bea914af87f7551962a3217edec215bcc91bf1c2df2c8ec593275379.
Preflight is still running, training not yet observed. Local curve unit73pass;
larger tiny train/freeze/replay suite37245 remains running (not duplicate).

Prepared separate cold-family screen, NOT imported by the training pilot.
Families semicircle/teardrop/chevron are excluded from all original native/
authored train, dev, calibration and known held controls. Preregister V11 cold
screen600 images, seed2211040000, unchanged candidate/threshold/numeric policy;
no model fitting/selection, reject any family/seed overlap with original course.
Require zero accepted errors and useful recall separately for EVERY family/task,
including known supported shapes, and zero accepted blank-image answers.
Original inference/pilot/verifier modules must load from hash-checked original
capsule in a fresh interpreter, never from current edited checkout. New authored
generator shares Pillow; this is not an independent photo/semantic blind exam.
Initial actual-capsule tiny subprocess QA8passed33.68s; it checks inference and
arithmetic replay, altered-threshold rejection, old evidence preservation.
Those are TOOL checks with random tiny weights, not cold mastery by V11.
Added explicit subprocess check=False/style fixes and early argument/source-path
checks afterwards; rerun required for latest bytes. Main index/workbook hashes
still exactly their original protected values.

01:20 UTC: local curve-focused37245 FINISHED149pass/2inapplicable skips/1FAIL
441.89s. Failure is an incorrect expected exception text in the new hostile
curve-policy test: actual verifier safely rejects altered protocol earlier by
its frozen input hash. Original failed XML preserved. V11 immutable capsule
contains this failing assertion and its remote preflight must finish/receipt
before any next run; do NOT rewrite/retry V11 source or declare it trained.
Fixed test now separately checks unresealed hash rejection and an adversarial
resealed protocol's semantic curve-policy rejection. Verifier behavior and
model acceptance unchanged. Latest cold-tool QA rerun69477 completed8pass30.19s,
style checks clean; backup chunk unit6pass0.41s.

01:22 UTC: exact affected quadratic fixture rerun30660 completed19pass,
117other fixtures deselected,76.66s. It now verifies both the original frozen
hash rejection and semantic policy rejection after an adversarial protocol
hash reseal. Verifier unchanged. V11 remote preflight38133 still running and
must fail its archived erroneous assertion; no training was observed/allowed.
Next fresh V12 preregistration: identical corrected V11 design, fresh seed11041,
V10 own warm checkpoint576eed15..., same sizes/criteria; it will be a NEW source
capsule and run name, not a repaired V11. Cold follow-up stays600 images but
use fresh seed2211041000 for V12. Its future cold families remain excluded from
all V12 training/development/calibration cohorts by construction and audit.

01:24 UTC: V11 remote38133 finished with1failed330pass2inapplicable skips,
362.09s; failure matches preserved local diagnostic, no model trained.
Original failed remote XML SHA
d77d213a1e849adcd8e1c6241d4e029133572d8fec3aa2b8a4b1e58c2394060a;
remote-preflight-failure.json statusREMOTE_PREFLIGHT_FAILED_NOT_TRAINED saved.
Fresh V12 launched **77691**, local composition-20261010-v12, remote
m33-composition-20261010-v12; source capsule SHA
ac36b1499ffedf979272992d62e5bbe66f6204b67d47ec9d3fb75134e72c1b82.
Pinned input transport-v12-input.py SHA2281f2678dd657d5ed2ec5cf6e03fc099a0ebec9020fb274c99dc9d9bc37a294.
Latest source combined primary/lexicon/textbook regression **39498** is live;
targetqa-sixhour-curve-full-regression-v1.xml, fresh fixture base
C:/Users/artio/AppData/Local/Temp/ai-brain-m33-sixhour-curve-full-20261010-v1.
Do NOT reuse this evidence base for another pytest run. Actual cold-tool fixture
contact sheet viewed: bounded visible semicircles/drops/chevrons and supported
shapes, distinct patterns retained. This is generator QA, not model mastery.
Only77691and39498 are live; don't duplicate. Still3h47m before earliest finish.

01:26 UTC: scoped V4 backup60971 completed and independently git ls-remote
confirmed commit46dff68b0b878cf0cbe7dac7d233d4c20811e4e3 (76 changed paths),
including completed V10, immutable failed V11, new tool/source and completed QA
receipts. Actual receipt is sixhour-backup-20261010-v4/push-receipt.json.
Do not infer backup failure from an earlier read attempt at nonexistent
backup-receipt.json. Main HEAD/index/workbook remain unchanged, SHA verified.
Next backup expected parent46dff68b0b878cf0cbe7dac7d233d4c20811e4e3.
New full regression39498 and V12 outcomes are not yet included in that commit.
D free824MB, W439MB. No files deleted; avoid duplicate older large datasets.

Primary NS-CL full text reread https://arxiv.org/html/1904.12584v1, sections3.2,
AppendixE/F.2: staged learning increases scene/question complexity; their random
visual-initialization ablation retained most concept accuracy with a small shape
drop. This supports testing own weights and gradual curricula, not importing
their pretrained ResNet or claiming the current closed-template network is
NS-CL. Their reported CLEVR result does not establish photo/textbook transfer
for our model. Readout attributes remain evidence rather than identity rules.

01:32 UTC checkpoint (NOT completion): latest combined regression39498 FINISHED
614passed/2inapplicable skips486.16s, XML SHA
cdefa14f664dca5b160867b9a412132437d0c743b3e8cbcc13d3a4c2706cf538.
Separate new cold-transport guard suite8passed0.51s, clean Ruff; these8were added
after combined file-list selection and are NOT falsely called one622-test run.
V12 **77691** preflight finished338passed/2inapplicable skips384.58s. Actual
remote experiment now contains90,657,600-byte dataset.npz, frozen protocol,
records/split/RNG receipts/contactsheet and joint directory; no final claim.
It is the ONLY live model run. Full regression/backup60971/graphs54040and74193
are complete; never restart old handles38133,37245,39498,69477 or30660.

Cold follow-up helper scripts/m33_composition_novel_remote.py is ready but NOT
run against V12 yet. After77691completes and its remote-receipt.json is present:
pin helper into D:/ai-brain-data/visual-lexicon/transport-cold-v12-input.py, run
with --repo W:/toolbox_IDEA/programs/IdeaProjects/ai-brain --reference
D:/ai-brain-data/visual-lexicon/composition-20261010-v12 --key
C:/Users/artio/.ssh/id_ed25519_ai_brain_m192 --count600 --seed2211041000
--child cold-family-screen-v1. Requires NEW child; authenticates original parent
capsule, source snapshots, actual inference hashes and every downloaded file.
Original reference model/numeric/policy frozen; no fitting or calibration.
If V12 base screen fails, retain failure and diagnose it; cold diagnostics may
still expose generalization but cannot make failed base model admitted.

Source-only small V5 backup planned next, expected parent46dff68b...; no old
large datasets recopied. D free823.9MB, W439.4MB; preserve all existing evidence.
Goal/heartbeat remainACTIVE until at least05:11:22UTC (~3h39m still required).
Continue meaningful work, not only repeated status polling. If both bounded
screens pass, audit exact provenance/inference and proceed to real-source image
controls and the next image block; neither synthetic screen closes strictM33U.

01:33 UTC: small source-only V5 backup pushed and independent ls-remote confirms
e727907de5bb6dd84e18ce7a0b29869f45a29c3b (26paths). NEXT backup expected parent
is this FULL SHA, NOT46dff68b. Previous large run artifacts were not recopied.
Current V12 joint training actually observed through1800steps, devCE0.0191082;
this is development only, not final accuracy/acceptance. Only model77691 live.
Canonical index/workbook again unchanged, D823.7MB free/W432.7MB during graph
cache refresh. Automatic goal continuation must resume77691, then complete its
source/replay/transport checks and fresh cold screen, and continue until deadline.
New source-only commit includes combined614/2 and separate8guard receipts;
this final handoff paragraph itself is newer than that backup. Do not pause or
complete goal now; user time window has not elapsed.

01:57 UTC: V12 training77691 COMPLETE and original CUDA inference/arithmetic
independently replayed. Joint checkpoint bdb1af182edd919439e8a9fa019e9a781ec943acdccded4b7a29b448c328f7dd.
Final/combinations accepted errors0/0, positive recall0.993889/1.0; transfer
and authored held control each1accepted error. NEEDS_WORK_NOT_PRODUCTION remains
correct. No retrospective threshold changes; all thresholds0.9. V12 inputs,
source capsule and exact hash are recorded above; transport receipt elapsed1492s.

New frozen-source cold-family screen24028 COMPLETE: 600images/3600questions,
0accepted errors, positive recall0.994580, unknown recall1.0, blank accepted0;
all family/task gates passed. The new contours are semicircle/teardrop/chevron,
not original train/dev/cal or held-control shapes. Shared Pillow, not photos.
This success does NOT override failed original V12 acceptance.

Real-source preparation completed before inspecting V12 finals: 11visually
reviewed source ROIs from2pages/2original Russian Belarus math PDFs. Original
bytes unchanged; fresh PDF110dpi rendering reproduced preview SHA exactly.
Source annotations examples/m33/visual_source_controls_v1.json fixed before
predictions. 110ordered composites/660questions are combinations of11assets,
NOT110independent source examples. Unsupported pink/orange/light-blue and
non-four-shape contours require UNKNOWN only within this bounded vocabulary.
Preparation v1/v2/v3 preserved, selected v3 adds executed-source/freeze/raw-ROI
provenance. Independent loader reconstructs actual RGB composite and gold from
raw crops/annotation, detects hostile changes even after receipt resealing.
Actual source-ROI/model-input contact sheets and both complete PDFpage previews
visually inspected; no clipping/neighbor/text contamination. This is nonblind
primary-agent labeling, not an independent semantic examiner/full-page ability.

Combined source/cold regression59471 COMPLETE29passed29.486s; transport8passed
0.245s. XMLs qa-sixhour-source-cold-combined-v1.xml and
qa-sixhour-source-transport-v1.xml confirmed from files after tool-output
truncation, not guessed from disappearance of a process handle. Actual original
capsule subprocess test for prepared sources61599 now live; after pass run
source-control-screen-v1 on remote frozen V12 with prepared v3, count110/seed0
(deterministic assembly, seed unused). Do not fit/calibrate on this assessment.
Temporary goal/heartbeatACTIVE; earliest finish still05:11:22UTC.

02:05 UTC: actual prepared-source subprocess61599 COMPLETE4passed35.97s,
then remote6769 COMPLETE authentic original V12 inference on real ROIs:
660questions,375accepted,71false assertions,positive recall0.690909,
unknown recall0.727273,blank accepted0. This is a material transfer failure,
not a mislabeled successful textbook stage. Breakdown: unsupported orange,
pink, light-blue irregular quad each20color mistakes; light-green rectangle
11color mistakes. Red/green triangles, yellow/red circle and pink rectangle
also have excessive refusal. Exact detailed per-source rows retained. Source
control is now EXPOSED; later scores on these same11assets are diagnostics,
NOTfresh independent exam. We must prepare untouched additional source ROIs
before a future candidate final. No existing annotation/threshold changed.

Next opt-in experiment: rich_curve_background_clear expands NEW training-only
quadratic stripe curvature and adds cubic curvature; original sinusoidal held
transfer remains unchanged. New palette authored exposure retains original
standard/diverse pixel algorithms, adds8unsupported training contour families
(parallelogram/kite included), explicit four unsupported color meanings,
broader known red/green/yellow/blue ranges and paper246..255backgrounds.
Held authored shapes stay star/pentagon/trapezoid; turquoise color is HELD
and never training/dev/cal. UNKNOWN is head scope, not forgotten words.
Independent palette-label/visual streams avoid color/background metadata cues.
No textbook source pixels used to train this block. This is a bounded domain
randomization/OOD exposure experiment, NOTa guarantee of external-source transfer
or the full OE uniform-posterior algorithm. Primary references read:
https://arxiv.org/abs/1703.06907 and https://arxiv.org/html/1812.04606v3.
An unrelated arXiv1806.05298lookup was recognized as unrelated and NOTused.

New unit QA v1 caught an unintended right angle in proposed kite geometry;
changed kite vertex before any training, v1failure preserved. Unitv2 COMPLETE
36passed8.82s. Tiny rich/palette training+replay regression85435 currently
finishing; v1 includes a stale Quadratic-only assertion string for new rich
protocol, fixed EXPECTATION, verifier rejection was correct/unmodified.
Need complete fresh v2 before launchV13. Graph35444 rebuilt successfully1005
files; qualified scenes queries not_found for untracked files, not proof of
no consumers. Confirmed pilot/verifier/controls calls with rg/source. Rebuild
again after opt-in profile structure stabilized. Next backup expected parent
e727907de5bb6dd84e18ce7a0b29869f45a29c3b; preserve user HEAD/index/workbook.

02:20 UTC continuation checkpoint, NOTcompletion: V6 backup29630 COMPLETE
143paths, exact remote ref independently confirms
5b60b7e4be3b26e6641be8d614682c5bfb955bd3. NEXTbackup parent this FULL SHA.
Includes completed V12, cold/source frozen assessments and sourcepreparations
v1-v3; main HEAD/index/XLSX exact protected hashes unchanged. New V13 artifacts
and new art source preparations below are newer than this backup.

Rich/palette local fixturev1 preserved1failed18passed75.12s (stale test message
expectation, correct verifier rejection), correctedv2 COMPLETE19passed/136
deselected79.97s. Scoped source/cold/package/backup regression61753 COMPLETE
39passed41.31s. Remote V13 **72734** preflight COMPLETE363passed/2inapplicable
skips393.53s, training observed joint1800 (NOTfinal); no other model job live.
Pinned driverD:/ai-brain-data/visual-lexicon/transport-v13-input.py SHA
ab95fbe8fecfcb96d7ff691f10bfedbb33405024fcb795071788a85b19fae74b.
Original capsuleSHA b3b5d834fc268810c5a04b78a0e65d3fab6dc954172e02a2d6a0d987265ed218.
Seed12043, V12joint warm bdb1af182edd919439e8a9fa019e9a781ec943acdccded4b7a29b448c328f7dd,
10000steps/schedule,9000native/3000authored/600held, richcurve/palette/IEEE,
same0.02smoothing/fourviews/JS0.2/spatialedges. Actual remote exposure preview
copied to v13/v13-exposure-preview.png and viewed: full figures/textures/new
colors, faint white figures on paper background. The full contact sheet will
be downloaded with normal completion; don't overwrite evidence.

Important PRE-FINALdata review: 3000palette exposure scenes have0visible
unsupported-color targets on supported shapes;1847unsupported-color/unsupported
shape,1846known-color/supported shape,1846known-color/unsupported shape. This
comes from both choices using i/side modulo3, NOTbackground RNG leakage or
oracle-as-model-input. It is nonetheless a coverage/confounding weakness.
V13 capsule remains immutable; let it finish as diagnostic and preserve this
limit. NEXTnew version should use independent palette-label draws so unfamiliar
colors occur on familiar ANDunfamiliar contours. Add regression on all four
color/shape familiarity combinations before V14. Do not retrospectively claim
the V13 palette corpus was fully factorized. Consider broader oval aspect ratios,
unconditional contour outlines for faint paper/white figures, and a bounded
risk-first calibration policy chosen on CALIBRATIONONLY if remaining evidence
warrants it. These are NEXTideas, NOTimplemented nor V13 activation.

Fresh art controls frozen before V13 final from another author/book family:
examples/m33/visual_source_controls_v2.json SHA
2414290fb18be06635c25dde0fba607e4acfbfab87a57410bf106fba556a1845.
Two complete page previews22/23 viewed.13ROIs:3visibly elliptical primary-color
swatches,9irregular solid paint blobs,1empty paper. Existing four-shape/eight
color head only; orange/purple/irregular contours outside this head are UNKNOWN.
No color-mixing reasoning or full-page understanding tested.156ordered scenes,
936questions are correlated pairings of13assets, not156sourceexamples. All
original PDF/page SHA verified via exact fresh PDF110dpi JPEG rendering.
Preparationv4 first revealed RAWCROPQA-gallery clipping with ROI>144px; actual
model tensors/rawcrops were correct. Fixed ONLYgallery cell sizing/wrapping,
added byte-exact large-ROI regression, v4 preserved, new v5 selected. v4/v5 model
datasetSHAidentical1e36113a8e064f9203fc83b469d84449feed1a784eca0548334a3fc9f83a2c7a.
v5actual gallery/modelinput sheets viewed, whole source objects without adjacent
text, raw ROI arrays and all156scene/gold rows independently reassembled.
Sourcegallery14passed2.63s. This remains nonblind primary-agent annotation;
user semantic review pending. Originalmath controls regenerated as sourcev6
with current course-source freeze: datasetSHAsame as v3, still EXPOSEDdiagnostics.
Course source hashes in sourcev5/v6 both exactlymatchV13capsule, tested.

After72734completion/actual remote receipt: pin latest novel transport to fresh
Ddriver, run V13source-control-screen-v1 with preparedsourcev5,count156,seed0
(unused deterministic assembly). This is FIRSTassessment on those art pixels.
Then source-control-screen-v2 with preparedsourcev6,count110,seed0 to measure
EXPOSEDmath improvements, never call second screen freshblind. Optionally
fresh cold-family-screen-v1 count600 seed2312043000, originalcapsule/policy/
numericbackend unchanged. If basefails, other diagnostics cannot promote it.

Current combined regression **35404** LIVE, selected original614-test file list
plus newsource/cold tools with fresh preserved fixture base
C:/Users/artio/AppData/Local/Temp/ai-brain-m33-sixhour-palette-full-20261010-v1.
XMLqa-sixhour-palette-full-regression-v1.xml not finished yet. Backup helper
subsequently adds OPTIONAL--stream-chunks: bounded Git blobs staged as ordinary
partNNN.bin, reread with cat-file and byte/SHA256reconstruction BEFOREref push,
no second90MBtemporary chunk directory. Old mode/restoration unchanged. New
separatebackup unitv1=14passed0.28s, v2=15passed1.58s including real disposable
Git blob roundtrip and hostile stored bytes/source mutation. This new15test
proof is separate from still-running35404's earlier imported backup module.
Use--stream-chunks for future large V13backup to avoid disk pressure; preserve
old chunk directories, no deletions. FreeD~491MiB,W418MiB,C14.9GiB. Only model
72734andregression35404live; all oldhandles COMPLETE. Goal/heartbeatACTIVE,
earliestfinish05:11:22UTC, ~2h50mstillrequired. Resume substantive work.

02:27 UTC checkpoint: graph65204 COMPLETE; source-only V7backup26856 COMPLETE,
95paths, independent ls-remote confirmed
24294937a1086a23f0f728768ddf26f2e8f9c20d. NEXTparent this FULL SHA, NOT5b60.
Full regression35404 COMPLETE662passed/2inapplicable skips565.32s, XML664cases,
SHAaa4e8a12b5ed2e549c3919862de0752b378275b4b6ecb09b9ba59d4ab41a3293.
It imported earlier backup/profile modules; do NOT falsely combine this count
with newer separate suites or call it validation of subsequently added options.

Fixed color/shape coverage weakness in NEWopt-in palette_independent profile,
keeping archival palette behavior untouched. Separate palette-label Bernoulli
draws choose unsupported colors independently of familiar/unfamiliar contour
group and scene modulo. Same known endpoints, paper RGB and 8exposure contours;
no new textbook pixels used to train. All16unsupported-color/familiar-shape
combinations present in3000visible-training-scene review. Actual familiarity
2x2counts:1221known/known,2471known/unknown,625unknown/known,1222unknown/unknown.
Turquoise and star/pentagon/trapezoid still absent training/dev/cal. Unit21passed
3.07s, actual tiny train/freeze/CUDA-contract-independent CPU replay fixture
81554 COMPLETE19passed/155deselected74.86s. Independent source review compared
current archival palette with actual V13capsule control code:30scene metadata
ANDRGBinputs byteidentical, current csourceSHA matched originalcapsule. This is
30-case compatibility proof, NOTall-possible-image proof. V13 remains original
palette and must retain its documented co-occurrence limitation.

Additional source-metadata hardening: rejectbool/zero/negative PDFpage aliases,
out-of-document page, invalid/bool/over300DPI and non-positive/bool/over8192pixel
dimensions BEFORErender/read. Old actualsourcev5/v6 validmetadata unchanged;
preparation-executed.py snapshots remain immutable. New23passed2.64s (9newguards).
No originalPDFchanged. Live V13 **72734** joint actuallyobserved6600step,
balanced devCE0.0176397; still NOwinner/result/source-control prediction.

Next model after V13 outcomes: V14 uses NEWfreshseed13045, warm frozen V13winner,
palette_independent plus same richcurve/IEEE/schedules/criteria. Choose pending
additional aspect/outline/risk-first experiments from real failure evidence,
not retrospective gate relaxation. New full regressionv2 planned against latest
independent/data/storage/metadata changes with a NEWfixture base. Source-only
V8backup should use parent24294937... and --stream-chunks, no previous large run
recopy. V13 completeartifact backup later must use --stream-chunks to save~90MB
of redundant temporary chunk copies; stream15-unitproof includes realGit read.
As always no autoactivation or strictM33Uclaim; goal/heartbeatstillACTIVE and
~2h44mremain before earliest05:11:22UTC. Never restart oldcompleted handles.

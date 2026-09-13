# M-33.6k.6 persistent capsule lifecycle

Strategy A is frozen: `PROTECTED_DETACHED_GIT_WORKTREE`. Runtime fallback is forbidden. The capsule is created before exact cross-platform qualification, its Git worktree is detached and locked, and its source root is outside quality, disposable, pytest, transfer, staging, production, evaluator, cleanup-managed, and temporary namespaces.

The stable Karina Python environment is bound rather than copied. It is outside all quality and disposable worktrees, is independently preserved through E31, and is re-verified from its resolved binary, environment/package manifest, `uv.lock`, `pyproject.toml`, import smoke, and hermetic startup receipt at every liveness boundary.

| Private resource | Producer | Lifecycle owner | Path class | First phase | Required through | Cleanup | Liveness verifier | Consumers | Deletion authority |
|---|---|---|---|---|---|---|---|---|---|
| implementation worktree | Git worktree bootstrap | R31 implementation owner | active implementation | R31 | E31 final quality | forbidden while active | exact Git SHA/status | qualification and publication | none before completion |
| persistent capsule root | capsule provisioner | final route controller | persistent protected root | before exact quality | E31 final quality | forbidden | `verify_m336k6_persistent_capsule` | all Karina phases | explicit post-success only |
| detached source worktree | capsule provisioner | capsule lifecycle | locked detached Git worktree | capsule creation | E31 final quality | forbidden | exact SHA/status/lock plus source manifest | preflight, materialization, production, replay, evaluation, runtime | explicit post-success only |
| capsule Git object store | capsule provisioner | capsule lifecycle | persistent Git store | capsule creation | E31 final quality | forbidden | Git worktree linkage and lock | source worktree | explicit post-success only |
| stable Python environment | environment authority | capsule lifecycle | persistent external environment | capsule creation | E31 final quality | forbidden | resolved binary and package manifest | every Karina Python worker | external environment owner after E31 |
| Git, SSH, Java, Javac and shell tools | platform authority | capsule lifecycle | stable executable | capsule creation | E31 final quality | forbidden | executable/JDK/dependency identities | transport and every Karina worker | platform owner |
| bootstrap and launcher | R31 implementation | capsule lifecycle | locked tracked source | capsule creation | E31 final quality | forbidden | source bytes in capsule manifest | every hermetic invocation | post-success capsule authority |
| candidate pool | F30 historical freeze | final-route authority | immutable public metadata | F30 | E31 | forbidden | semantic and byte hashes | acquisition and selector | none |
| historical F26 vault and TAR | F26 controller | historical evidence owner | immutable historical vault | F26 | indefinite | forbidden | full file/tree manifest plus TAR hash | recovery audit | user only |
| recovery bundles | recovery manager | recovery evidence owner | external evidence | recovery checkpoint | E31 | forbidden | file hashes | recovery and final audit | user only |
| storage reservation | resource manager | final route controller | active reservation | pre-Q31 | post-F31 validate-only | forbidden until explicit release | size/allocation/content receipt | storage gate and controller handoff | phase-15 release only |
| quality worktrees | quality orchestrator | exact-quality owner | disposable quality | exact quality | quality receipt complete | pre-freeze eligible | exact SHA/status and no active process | quality only | PRE_FREEZE cleanup plan |
| disposable worktrees | disposable orchestrator | rehearsal owner | disposable protocol | survival rehearsal | public rehearsal receipts preserved | pre-freeze eligible | terminal marker and no active process | rehearsal only | PRE_FREEZE cleanup plan |
| materialization root | stage worker | route controller | current route private | route execution | route terminal | never while current | stage receipt chain | production and publication | POST_SUCCESS only |
| production and replay roots | production workers | route controller | current route private | production | H31 plus evaluator inputs bound | never while current | production/replay receipts | H31 and evaluator | POST_SUCCESS only |
| evaluator and runtime roots | evaluator worker | route controller | current route private | post-H31 evaluation | E31 final quality | never while current | evaluator/runtime receipts | E31 | POST_SUCCESS only |
| official F31 artifacts, ledgers, vault and selected snapshot | official controller | final route controller | official immutable/current | F31 or creation | E31 final quality | forbidden | freeze, ledger, vault and snapshot receipts | official route | none before E31 |

The cleanup planner rejects equality, ancestors, descendants, resolved symlink/reparse targets, active-process references, current-receipt references, and resources whose lifecycle has not ended. The exact preservation rejection is `PRESERVATION_SET_INTERSECTION`. There is no cleanup mode from F31 creation through E31 publication; the only deletion in that interval is the separately authorized storage-reservation release immediately before the official acquisition reservation.

Unclassified private resources: 0. Frozen resources without lifecycle owner: 0. Frozen resources without liveness verifier: 0.

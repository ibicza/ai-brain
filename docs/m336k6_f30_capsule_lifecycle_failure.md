# M-33.6k.6 F30 capsule lifecycle failure

The historical F30 remains immutable at `ff28a2c13e31c2d35d56991af69b0cb62d18b504` and remains Outcome C.

The exact classification is `FROZEN_PRIVATE_CAPSULE_DEPENDED_ON_DELETABLE_QUALITY_CHECKOUT`. The frozen public capsule binding described a direct project-Python execution environment, but its private source checkout and private capsule root were children of the Karina exact-quality workspace. That workspace was correctly classified as a completed `STAGING_TREE`. Its cleanup receipt is `d07bf3b4fc6e8dbe9c0fbb396e5f2ccc762166ab935c3910c5e1a9eff01058ef`.

Cleanup did not reject the workspace because the F30 capsule resources had no immutable lifecycle owner in the cleanup input and their paths were absent from the preservation set. The cleanup assessment therefore observed zero preservation intersections and deleted the completed quality workspace before Q30 and F30 were created. Post-F30 validate-only later passed local hermetic startup and failed the remote host preflight before any route ledger or one-shot reservation because the frozen private checkout no longer existed.

All F30 official counters remain zero, the F30 vault is absent, new final source-body bytes remain zero, and there are no unclassified causes.

M-33.6k.6 removes the lifecycle coupling by provisioning one locked detached worktree in the dedicated persistent Karina capsule namespace before exact qualification. Its source, Python environment, executable identities, content manifest, lifecycle policy, and liveness receipt are frozen and included in an immutable preservation set through E31 final quality.

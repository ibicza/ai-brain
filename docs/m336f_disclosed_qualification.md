# M-33.6f disclosed qualification

Status: `NOT_RUN_EXACT_R21`.

The latest development rehearsal passes closure, one-shot selection, production, replay, independent SPDX, independent compiler/semantic evaluation, exact field evidence, five-root trust holdouts, installation/runtime and producer contracts. Its platform-neutral semantic artifact hash is `7c912d880b2a71686f1d2064c32645b26fca8832422d3d2482b970c3e990dfdf`. It is explicitly non-authoritative because it ran before the R21 commit.

The exact chain starts with the selector-free `m336f_run_disclosed_qualification.py`: it re-verifies the complete vault, frozen authority, historical qualification equality and the current 30-entry disclosure registry, and emits freshly bound census inputs with zero selector reservations or invocations. Only its PASS output may enter the compiler-closure runner that owns the single selector reservation. The closure runner verifies the complete qualification report and summary and binds both hashes into the selector ledger, selected manifest, and selector receipt.

After R21 is committed, the complete chain must run once from a clean exact-R21 worktree on Windows and Karina. Q21 is forbidden unless all mandatory criteria pass, including byte-identical platform-neutral output and both full quality suites.

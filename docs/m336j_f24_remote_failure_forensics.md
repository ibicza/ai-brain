# M-33.6j F24 remote failure forensics

The exact historical F24 commit is `4891de1c3a0f6ba2d5d012ab5189dbb5222ba6bd`. Its final controller was invoked through non-interactive SSH with no pseudo-TTY, login shell, or startup profile. The unchanged remote command exited `127` before any acquisition or route ledger existed because the first bare executable token, `uv`, was not resolvable. The normalized failure is `BARE_UV_NOT_RESOLVABLE_IN_NONINTERACTIVE_SSH`.

The historical non-interactive PATH had nine entries. `uv` and `python` were not resolvable; `python3` and `git` were resolvable. The exact PATH and all absolute executable paths remain private. The complete public-safe logical inventory is recorded in `artifacts/m336j/f24_remote_executable_inventory.json`.

Two production-reachable F24 call sites used the same unsafe prefix. `_invoke_karina_worker` built `uv run python` for materialization and production worker requests. `_validate_final_controller_inputs` built `uv run python` for the pre-acquisition host preflight. The failure therefore happened before acquisition reservation, source download, vault mutation, selector reservation, or selector invocation; all corresponding historical counters remain zero.

Q24 quality did not exercise either SSH path. `scripts/m336i_run_exact_quality.py` selected its already-running local `sys.executable` and used it for the local route-preflight subprocess. Its Karina quality invocation likewise ran the quality process inside an already prepared interpreter environment; it did not invoke the F24 Windows controller's non-interactive SSH command construction.

R25 removes both `uv run python` call sites from the active Karina route. The replacement invokes a frozen absolute project interpreter through a typed, deterministic command plan under a minimal environment.

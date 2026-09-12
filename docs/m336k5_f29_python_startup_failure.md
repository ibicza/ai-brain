# M-33.6k.5 F29 Python startup failure

F29 remains immutable at `c661ffa8b0300776c4d8f502fcbea6f72c912a42` with historical `OUTCOME C — BLOCKED`.

The exact F29 `validate-only` command shape was reproduced before any implementation change from a parent environment where `PYTHONNOUSERSITE` was absent. The child used `-B` without `-s`. At interpreter startup, `sys.flags.no_user_site` was `0`; the environment variable remained absent. The user-site directory was not present in `sys.path` on this host and `site.ENABLE_USER_SITE` happened to be false, but the frozen verifier correctly rejected the process because the complete startup contract was not satisfied.

The exact exception was `ai_brain.stage3.acquisition.m336k2_protocol.M336K2ProtocolError: M336K2 user-site loading is not disabled`. The failed validation wrote no route event or ledger, made no source request, created no vault file, and invoked no controller, acquisition, selector, or evaluator.

Root-cause classification: `AMBIENT_PARENT_ENVIRONMENT_BYPASSED_HERMETIC_BOOTSTRAP`.

Unclassified root causes: `0`.

The required repair belongs at the external process-start boundary. Environment changes made after Python has initialized `site` cannot establish the required startup invariant. The recovery route therefore needs a tracked outer launcher, `-s -B`, an allowlisted environment, and a standard-library bootstrap that verifies effective startup state before importing project code.

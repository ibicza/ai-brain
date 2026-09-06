# M-33.6g artifact confidentiality model

Every current M-33.6g artifact has exactly one role:

- `PUBLIC_DERIVED_PACK`: loadable, installable, queryable source-free pack bytes.
- `PUBLIC_COMMITMENT`: hashes and counts binding private replay inputs without carrying them.
- `PUBLIC_SAFE_RECEIPT`: path-free proof results and counters.
- `PUBLIC_PLATFORM_TELEMETRY`: binary hashes and normalized host observations without paths.
- `PRIVATE_SOURCE_INPUT`: portable vault-relative identities used only by sealed replay.
- `PRIVATE_HOST_OBSERVATION`: runtime `Path` objects used to verify a local JDK.

Public writers reject private role names, private field names, reversible source payloads, Java excerpts, filesystem paths, traversal, and unknown candidate-pack entries. Private manifest writers resolve canonical ancestry and reject Git worktrees, public roots, installation roots, symlinks, reparses, and traversal. The vault root is supplied out of band and never serialized.

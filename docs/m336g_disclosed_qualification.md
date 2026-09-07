# M-33.6g exact-R22 disclosed qualification

The authoritative disclosed run is bound to R22 `5f26b8f710d1a67314a83de7a569b7be7c9098a6` and passed on Windows and Karina. It reused only the disclosed registry and sealed historical vault; no new candidate source body was acquired.

The selector ledger records one reservation, one invocation, and zero reruns. It selected 180 files from 5 roots with a maximum root contribution of 63. The selected SourceEntryId set has zero difference from R21.

Production produced 1587 proposals: 1575 trusted and 12 withheld. Compiler-blocked declarations are 12; trusted blocking targets and post-trust pack failures are zero.

Both independent evaluations report trust precision 1.000000, safe trust coverage 0.957447, location precision/recall 1.000000/0.964156, semantic precision/recall 1.000000/0.964156, field-evidence exactness 1.000000, SPDX agreement 1.000000, and zero wrong trusted items.

The public pack has exactly 11 recursively contracted entries. `java_production_closure.json` and `java_replay.json` are absent. Public-pack integrity and sealed-source deterministic replay are separate passing proofs; replay reconstructed the public pack with zero byte differences. Installed runtime passed without source inputs.

The combined publication-boundary scan reports zero fresh-source leaks, source windows, reversible source payloads, absolute paths, private artifact roles, and unknown pack entries. Raw source and excerpts remain denied from publication. No scanner, family, path, proposal, or golden exception was added.

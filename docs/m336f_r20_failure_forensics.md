# M-33.6f exact-R20 failure forensics

The immutable baseline is R20 `8e0b542bd180e33ae38fea81d53e45195d4a918e`, whose parent is E19 `74f7740aea907cd2b4a7e0b885a5d4c60e7aa2db`. The primary R20 production and evaluation artifacts were re-read; aggregates were not reconstructed from memory.

Count-first trust evidence is: 1,768 proposals, 887 actually trusted, 1,143 independently expected trusted, 858 correct trusted, 29 wrong trusted, 641 correct withheld and 285 incorrect withheld. Trust precision is `0.967306`; recall and safe coverage are `0.750656`; legacy coverage is `0.776028`.

All 29 disagreements were compiled in `CURRENT_SELECTED_SET`, `SELECTED_PLUS_INTERNAL_SOURCE_CLOSURE`, `ALL_ANALYSIS_ELIGIBLE_FILES_FROM_THE_SAME_ROOT` and `EXACT_FROZEN_PRODUCTION_CLASSPATH` contexts. Current/frozen each compiled 180 files and produced 2,386 normalized diagnostics; selected-plus-internal compiled the exact 83-file affected-root closure and produced 17; the complete 103-file analysis-eligible root compiled with zero diagnostics. Source-unit-unbound and malformed-output counts were zero in every context. Every row is classified `MISSING_SELECTED_INTERNAL_TYPE`: the applicable header or enclosing-type diagnostic remains identical in the current/frozen context and disappears with internal closure and the complete analysis-eligible root. No row was classified as a genuine declaration error, external dependency, compiler mismatch, location-mapping error, multiple cause or unresolved.

The four v2 context reports bind semantic compiler identity `3ccdf9ac1127058ae9152c913fa03f246b860227bee28e4ca69f4418358c231f`. Current/frozen report hash is `3b62e66f10d762309736adc07ce38e9d1d7c2b967b7aa781b934243ce4b448f9`; internal-closure report hash is `5312968a0d08ed7b3c8ba7843e8e663527ba5d5367a8dfd38dac33c72285ba6b`; same-root report hash is `6dd990a4346034788475ca6493fca0bea4dcb08628c9b88359aeda56ebf1f035`. The public forensic report hash is `7dfb936daee642240d8b3b7a989248e9d6f305cbdc68cd91a7b3e332929b56cd`.

The only field-evidence defect is `content.generic_constraints[0]` on proposal `proposal.a20a7d3907ae07d1aebf3ae3b38a5493`: one wrong row out of 66,943. The category is `PRODUCTION_EXTRACTION_WRONG_GENERIC_OWNER`; production selected the enclosing type parameter instead of the callable-owned type parameter. The repair changes the generic extraction rule, not the proposal identity.

The only R20 platform artifact with byte differences is `independent_license_evaluation`. Its four host measurements and telemetry-derived report hash account for five field differences; semantic field differences are zero. M-33.6f separates this payload into count-first semantic evidence and host telemetry.

Public-safe primary reports are stored under `artifacts/m336f/`. They contain identities, hashes, spans, normalized codes and decisions, but no Java source text, excerpts, absolute paths or raw localized compiler messages.

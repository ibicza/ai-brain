# M-33 black-box freeze protocol

## Boundary

F12 freezes all implementation, schemas, tests, evaluator logic, source adapters,
selectors, authority domains, thresholds, resource limits, and final task counts.
The four final source bodies were not downloaded or processed before F12. The
development corpus uses geology prose and the fictitious `OrbitLedger` API; it
does not overlap the sealed chapters or OpenJDK types.

The seal is `config/m33_final_source_selectors.json`. Its byte hash, F12 commit,
roadmap hash, provider registry hash, capability registry hash, evaluator hash,
and graph state form the freeze receipt.

## Permitted sequence

1. Commit F12 and record a clean-tree freeze receipt.
2. Acquire only the sealed selectors with `scripts/m33_acquire_final_sources.py`.
3. Record original download hashes, inert snapshot hashes, redirects, versions,
   licenses, timestamps, and transformation identities.
4. Author source-native goldens without importing compiler output.
5. Run the frozen pipeline once over every bundle.
6. Select Outcome A, B, or C without changing frozen code.

After F12, a gate rejects changes to `src`, `schemas`, `scripts`, `tests`,
`pyproject.toml`, `uv.lock`, capability/provider definitions, the selectors, or
the evaluator. H12 contains final data and source-specific reports only. E12 is
restricted to evidence, metrics, performance, graph, and final reports.

## Failure policy

No threshold, regex, schema, provider, or capability may be tuned after source
reveal. A safe low-recall result is Outcome B. Any false automatic trust,
runtime shortcut to a source/golden, silent applicability loss, saga authority
loss/duplication, or frozen-core change is Outcome C.

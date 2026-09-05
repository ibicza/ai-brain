# M-33.6e graph impact map

## Exact-E19 graph baseline

The project graph was rebuilt in the isolated M-33.6e worktree before broad source reading. It is bound to branch `exp/stage3-m336e-integration-closed-java-freeze-v4` at exact E19 `74f7740aea907cd2b4a7e0b885a5d4c60e7aa2db` and contains 13,811 persistent nodes, 96,147 edges and 1,008 files. The full build parsed 1,009 files and emitted 15,158 nodes / 98,057 edges before persistent post-processing.

`status`, `detect-changes`, `search`, `callers_of`, `callees_of`, `tests_for` and depth-two `impact` were run. The initial change detector found no changed functions/classes, affected flows or test gaps. Its 52-file comparison set is a configured-base comparison; the worktree itself was clean.

## Navigation findings

- `acquire_qualify_select_once` owns acquisition, authority receipts, vault sealing, freshness overlap and selector ordering. It calls `_select_once` only after writing a process-external sentinel, but without a prior capacity proof.
- `_select_once` calls the standalone `_contains_real_callable_type` predicate and directly reads untyped path strings. Its known callers are the M-33.6d orchestration and the exact-180 selector regression.
- `index_java_bundle` is the production source-index authority. Its depth-two file impact is 50 directly changed nodes, 114 impacted nodes and 43 additional files.
- `propose_java_knowledge` consumes the bundle, physical segmentation and `JavaSourceIndex`. Its depth-two file impact is four directly changed nodes, 68 impacted nodes and 31 additional files.
- `PublicFinalArtifactContractRegistry` owns strict path matching, canonical JSON parsing, recursive field validation and cross-field invariants. Its module impact is 32 directly changed nodes, 22 impacted nodes and 13 additional files.
- `verify_disclosed_java_registry` verifies content-addressed entries and walks manifest parents, but the existing append implementation sorts the whole set and does not bind a typed append receipt. Its module impact is 20 directly changed nodes, 39 impacted nodes and 22 additional files.
- `test_disclosed_registry_remains_append_only_and_complete` has no downstream graph impact but directly freezes the invalid six-entry cardinality assumption.
- The old portable verifier is in `m336d_final_pipeline.py`; the local vault writer/manifest implementation is in `m336d_contracts.py`. Both must route through the same new primitive rather than receive parallel fixes.

## Planned repair boundary

M-33.6d code and evidence remain a read-only legacy surface. M-33.6e will add a versioned integration layer for canonical source identity, portable vault paths, selectability census and feasibility, the persistent run ledger, producer-contract compatibility, and append-only registry receipts. Existing production indexing/proposal semantics will be reused as the census authority rather than duplicated. The only historical test edit is replacement of exact cardinality with immutable-original-entry and append-chain invariants.

After structural implementation, the graph must be rebuilt and the same query/impact set rerun. Source/tests remain the final authority where graph resolution is ambiguous or absent.

## Post-repair graph

After staging only the intended R20 paths, the full graph build parsed 1,042
files and emitted 15,420 nodes / 102,460 edges. Persistent post-processing
retained 14,073 nodes, 100,495 edges, and 1,041 files. The increase from the
exact-E19 persistent baseline is 262 nodes, 4,348 edges, and 33 files.

The repeated search now resolves `run_fresh_acquisition_and_preflight` at its
qualified M-33.6e location. `callers_of` returns the exact acquisition wrapper
and the infeasible-preflight regression. `callees_of` resolves the frozen pool
validator, persistent ledger, authority registry, portable vault builder and
verifier, production index, source-entry binding, census, feasibility solver,
one-shot selector, and external materializer. `tests_for` and source inspection
confirm direct coverage for the registry append/parent checks even though the
initial unstaged graph reported them as gaps.

Depth-two impact reports 46 affected nodes for the staged repair surface. The
highest-risk existing node remains `verify_disclosed_java_registry`; its direct
tests cover valid 30->31/54/78 appends, immutable original bytes, deletion,
replacement, reordering, duplicate identities, wrong previous manifest, and a
skipped parent. The graph also exposes an ambiguous short `verify` call between
the authority and SCM providers, so the final review used qualified definitions
and executable tests rather than treating that graph edge as proof.

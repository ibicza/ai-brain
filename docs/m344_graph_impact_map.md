# M-34.4 graph impact map

## Scope and baseline

- Exact base: `f83a4b72de5843d699f971932b0dd28c872ab533`.
- Branch: `exp/stage3-m344-oracle-free-java-freeze`.
- The graph was rebuilt before broad reading with `scripts/update-code-graph.ps1`.
- Baseline build: 649 parsed files, 10,173 nodes, 71,368 primary edges.
- Baseline post-process: 779 files, 12,803 nodes, 96,870 edges.
- Staged pre-F13 build: 664 parsed files, 10,297 nodes, 72,873 primary
  edges; post-process: 794 files, 12,927 nodes, 98,358 edges.

The first pass used `status`, `detect-changes`, `search`, `callers_of`,
`callees_of`, `tests_for`, and `impact --depth 2`. Exact search subjects were:
`run_java_trust_pipeline`, `bind_java_trust`, `verify_trust_bound_batch`,
`JavaTrustDecision`, `JavaTrustClosure`, `VerifiedJavaTrustAuthorization`,
`java_goldens`, `java_seal`, `JavaSemanticProposalOracle`, `java_source_index`,
`java_type_universe`, `java_evidence_policy`, `java_evidence_transforms`,
`compile_provisional_pack`, `review_proposal`, `JavaFreezeProtocolReport`, the
pre-freeze gate, replay, and process audit.

## Dependency finding

The legacy production path is
`run_java_trust_pipeline -> bind_java_trust -> _golden_exact`, with direct
dependencies on `java_goldens` and `java_seal`. Golden identity then propagates
through the legacy trust decision, closure, bound batch, and replay.

The replacement closure begins at `run_java_acquisition_pipeline` and reaches
source ingestion, physical Java indexing, Java 21 type resolution, proposal
construction, evidence-policy transforms, structural verification, and
production replay. Its recursive Python import closure contains no evaluator,
golden, seal-evaluation, or javac-oracle module. The independent edge is
one-way: `java_production_evaluator -> java_production`; no production node
reaches the evaluator.

The staged graph reports 13 direct production callees: Java policy recognition,
release construction/verification, parser verification, production evidence
policy loading, source indexing, segmentation, proposal construction,
structural verification, evidence construction, and production trust binding.
It reports only the two orchestration scripts as evaluator callers and four
tests for the production entry point. Depth-2 impact reports 42 affected nodes.

Graph-selected tests were the M-34.1/M-34.2/M-34.3 Java integration and replay
tests plus the new `tests/test_m344_oracle_free_java.py`. Broad reading excluded
unrelated model training, UI, episodic-memory, relationship-memory, and other
domain implementations. Source and tests were used to verify graph findings
because a graph index can be stale or ambiguous.

The graph is rebuilt and frozen again at F13. H13 and E13 are required to show
data-only and evidence-only changes respectively.

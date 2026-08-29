# M-33 graph impact map

## Exact baseline

- E11: `b55b61148d12386d6f2132b136b11f8dca859a7e`
- H11 parent: `af508a130b6e496f907254593387b13e4a73d2ce`
- branch: `exp/stage3-cross-domain-blackbox`
- roadmap SHA-256: `8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`

The graph was rebuilt before broad source reading. The parser indexed 453 files,
6,023 nodes, and 58,898 edges. Persistent post-processing reported 583 files,
9,091 nodes, and 84,726 edges. `detect-changes` and depth-2 impact against E11
were empty before implementation.

## Exact graph-first queries

```text
.\scripts\update-code-graph.ps1
uvx --from code-review-graph code-review-graph status
uvx --from code-review-graph code-review-graph detect-changes --base b55b61148d12386d6f2132b136b11f8dca859a7e --brief
uvx --from code-review-graph code-review-graph search <symbol> --limit 3
uvx --from code-review-graph code-review-graph query callers_of <qualified-name>
uvx --from code-review-graph code-review-graph query callees_of <qualified-name>
uvx --from code-review-graph code-review-graph query tests_for <qualified-name>
uvx --from code-review-graph code-review-graph impact --base b55b61148d12386d6f2132b136b11f8dca859a7e --depth 2 --max-results 5
```

Search covered proposal generation/verification, pack compilation/evaluation,
generic educational and conversational providers, `TutorSagaCoordinator`,
provider/capability/domain registries, source ingestion, and the scalar solver.
The class-level caller queries under-report Python dynamic dispatch; source and
tests are the final authority.

## Expected F12 blast radius

- Acquisition models, verification, compilation, field evidence, independent
  metrics, semantic task keys, and natural-document extraction.
- Typed executable pack evaluation and installation closure.
- Provider-specific schemas and unit-aware affine solving.
- Persistent generic education/conversation plus real-store saga recovery.
- Development-only tests, freeze selectors, and final evaluator.

F12 and H12 graph states will be appended after their respective boundaries.

## Pre-F12 implementation state

After the implementation working tree (before staging new files), a full rebuild
reported 453 parsed tracked files and 6,081 syntax nodes with 59,583 edges;
persistent post-processing reported 583 files, 9,149 nodes, and 85,404 edges.
Depth-2 impact against E11 found 248 directly changed nodes, 70 total impacted
nodes, 14 affected tracked source files, and risk score 0.85. The graph's test
gap report did not associate dynamically parameterized saga tests with several
generic service methods; source inspection and the explicit 14-point crash
matrix are the authority. A second rebuild after staging is required so newly
added modules and scripts enter the exact F12 graph.

After staging all F12 paths, that rebuild parsed 467 tracked files and produced
6,171 syntax nodes with 60,787 edges. Persistent post-processing reported 597
files, 9,238 indexed nodes, and 86,590 edges. This is the graph state immediately
before the F12 gate; the graph cache remains uncommitted.

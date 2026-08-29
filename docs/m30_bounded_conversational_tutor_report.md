# M-30 final exact-H9 report

## Outcome and release identity

- **OUTCOME A — bounded conversational tutor works.** Phase-0 authority fixes,
  controlled multi-turn conversation, public confirmation, observable progress,
  deterministic recommendation and historical replay all pass.
- Branch: `exp/stage2-conversational-tutor`.
- H9: `0da9e8a316698257b7726bc406618ba3e8669e32`.
- Exact parent: E8 `28fa0e3429ad08650b7a61396bbd62be7201b933`;
  H8 remains `0a7522cfe104f23981fc971ddde00c993f0f2812`.
- H9 tree: `ca4554f774d28d2534256fb50af1fff769bee2dc`.
- E9 is the evidence-only child containing this report and machine-readable gate
  outputs. Its SHA is reported after commit creation to avoid a self-reference.

## Project graph

- Exact-E8 baseline: 8,323 nodes, 77,964 edges, 474 files.
- First M-30 refresh: 8,501 nodes, 79,264 edges, 504 files.
- Final H9-candidate refresh: 8,522 nodes, 79,586 edges, 504 files; 79
  E8-relative files, 219 changed functions/classes and 35 affected flows.
- Queries used: `status`, `detect-changes`, incremental/full `update`, qualified
  `search`, `callers_of`, `callees_of`, `tests_for`, and depth-two `impact`.
  Source and tests were used to verify every graph-selected relationship.

## Exact-SHA gates

| Gate | Windows | Karina |
|---|---:|---:|
| Full pytest | 774 passed, 961.47s | 774 passed, 257.00s |
| M-25 through M-29.2 prior regressions | 298 passed, 852.25s | 298 passed, 205.12s |
| Current + stale-history backup/restore | 2 passed, 26.97s | 2 passed, 12.25s |
| M-30 acceptance | PASS | PASS |
| Worktree before/after | clean | clean |

Windows also passed `ruff format --check` over 357 files, `ruff check`, and a
public-DTO CLI smoke for `chat-start`, `chat-turn` and `chat-progress`. The CLI
surface test covers all required chat commands. M-25.1 blind reopen was excluded
exactly as requested; its non-blind trusted coverage remains in the selected
suite.

## Acceptance and security evidence

- 5,000 balanced RU/EN scenarios, including 1,000 ten-turn conversations;
  50,000/50,000 turns parsed and transition-checked.
- All 12 forbidden state transitions rejected; wrong transitions accepted: 0.
- 10,000 progress sequences projected identically; projection mismatches: 0.
- 2,000 recommendation states; wrong deterministic recommendations: 0.
- 12 concrete pending-action integrity/context/expiry/single-use cases;
  accepted: 0. Double, cross-conversation, stale-dependency and unconfirmed
  execution: 0.
- 1,000 injection strings; action executions: 0. Partial composite execution,
  grading/progress override and automatic memory writes: 0.
- Phase 0: 100 upstream fact mutations accepted as current: 0; 500 non-catalog
  closure mutations accepted: 0; 500 incomplete canonical plans accepted: 0;
  1,000 public node/hash probes leaked: 0.
- Cross-learner leakage, stale-grading progress, opaque trait inference, hidden
  tool execution and public hidden-data leakage: 0.
- Trusted conversation/progress imports load no `torch`; source boundary has no
  runtime network client imports. The benchmark observed 0 runtime chemistry
  executions.

Windows and Karina acceptance JSON are byte-identical, SHA-256
`a1c4693719576a32efe90adc62e0ae1cd7ceda35ad823e0ddb330fc72c7efcb1`
after repository LF normalization.

## Catalog authority and determinism

- Catalog schema v4 contains 2,000 entries, 2,000 distinct semantic keys and
  2,000 distinct graphs; 1,900 entries bind offline tool receipts and 100 bind
  exact fact replay.
- Catalog logical hash:
  `27e4be229eac94813ee96e6a2fe457432d15c577742ca9c812a8b42cead37b28`.
- File SHA-256:
  `d59ca6f5b37375a07583a422f7ab35d7241aec349272f1beb8c3f012601e7e60`;
  53,994,760 bytes.
- Karina independent offline rebuild completed in 23.105191s and was byte
  identical to the tracked Windows artifact.
- Exact claim/evidence/source/derivation/upstream/value replay rejects retracted
  provenance and current-value changes. Runtime sessions must resolve to exactly
  one installed catalog entry. FULL/SOLUTION plans are exact canonical plans.

## CPU performance

Each row is `p50 / p95 / p99 ms; throughput/s; peak Python bytes`.

| Stage (count) | Windows | Karina |
|---|---|---|
| Turn parse (10,000) | 0.072500 / 0.092900 / 0.106500; 12,732.586; 373,661 | 0.043181 / 0.053220 / 0.056756; 21,723.677; 375,869 |
| State transition (10,000) | 0.000200 / 0.000300 / 0.000300; 986,767.449; 322,864 | 0.000130 / 0.000150 / 0.000160; 1,528,564.894; 322,872 |
| Pending prepare (10,000) | 0.079100 / 0.089400 / 0.111800; 12,190.374; 328,200 | 0.053401 / 0.057147 / 0.058089; 18,404.862; 329,412 |
| Pending confirm (10,000) | 0.220300 / 0.242000 / 0.297800; 4,445.534; 777,861 | 0.136045 / 0.140474 / 0.144171; 7,276.112; 777,823 |
| Progress append (1,000) | 5.081400 / 5.767100 / 6.060000; 194.307; 513,429 | 0.298290 / 0.328046 / 0.348465; 3,295.293; 513,445 |
| Progress projection (10,000) | 2.027900 / 2.160800 / 2.397100; 489.260; 827,916 | 1.238006 / 1.254538 / 1.270969; 805.664; 827,927 |
| Recommendation (10,000) | 0.081500 / 0.089900 / 0.118300; 11,891.165; 325,877 | 0.048802 / 0.052368 / 0.053150; 20,140.224; 325,768 |
| Presentation (20) | 490.767950 / 498.309300 / 498.309300; 2.046; 2,437,291 | 182.022244 / 184.835881 / 184.835881; 5.537; 2,433,546 |
| Answer submission (20) | 504.622550 / 521.807600 / 521.807600; 1.977; 2,392,114 | 189.572107 / 190.450542 / 190.450542; 5.300; 2,392,386 |
| Exact grading (100) | 8.099650 / 8.522500 / 12.167000; 121.623; 100,307 | 4.989511 / 5.028239 / 5.042015; 200.439; 209,931 |
| Hint (20) | 488.859150 / 498.880100 / 498.880100; 2.042; 2,397,204 | 186.486614 / 187.115335 / 187.115335; 5.397; 2,395,791 |
| Solution (20) | 529.024300 / 538.529200 / 538.529200; 1.898; 2,955,390 | 216.920480 / 219.653220 / 219.653220; 4.602; 3,693,152 |
| Replay (10) | 3,094.963850 / 3,160.445600 / 3,160.445600; 0.323; 9,191,902 | 1,546.549448 / 1,551.605630 / 1,551.605630; 0.645; 8,716,379 |
| Structural backup (1) | 2,904.952200; 0.344; 1,013,862 | 1,523.372384; 0.656; 1,009,654 |
| Authority verification (1) | 92,549.314300; 0.011; 6,568,354 | 46,620.413217; 0.021; 6,287,559 |

Normal turns use bounded dependency closure; the expensive full authority verify
is measured separately and is not executed on each turn.

## Scope and limitations

The release remains chemistry-only and finite controlled RU/EN conversation. It
does not provide unrestricted chat, neural grading authority, personality or
intelligence inference, runtime network access, automatic FactMemory/RuleMemory
writes, or targeted conclusions from ambiguous diagnosis. Progress derives only
from observable trusted events. New calculations require explicit confirmation.
Historical stale sessions remain inspectable and backup-able but cannot authorize
new grading. No moral, moderation, refusal, political, ideological or topic
policy was added.

## Recommendation

Proceed to M-31 with broader educational-domain expansion only through new
catalog adapters that preserve exact entry anchoring, public DTO boundaries and
the same event/projection replay contracts. Treat any neural language surface as
non-authoritative and evaluate it separately.

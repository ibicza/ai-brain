# M-34.2 pre-freeze semantic integrity report

## Scope and release boundary

- Branch: `exp/stage3-m342-pre-freeze-integrity`
- Exact base: `7629cf0088803cdf7cf3f9816d0d76cd26dd5e7f`
- Implementation commit: `8f4802e0cf2199b4e9bae1552492c5115fa1123d`
- Untouched/final evaluation executed: **no**
- Development decision: **READY_FOR_FRESH_FREEZE**.

M-33 Outcome C remains outside this branch's ancestry. No Stage-1, H11/E11,
topic, moderation, refusal, political, personality, or NSFW policy layer was
changed.

## Production resolver

`JavaTypeUniverse` is sealed from the immutable source declarations and a
checked-in Java 21 `ct.sym` inventory (4,992 platform symbols). Resolution uses
this precedence and no global simple-name fallback:

1. primitive;
2. method/type variable with first-bound erasure;
3. lexical/member type;
4. existing explicit single-type import;
5. same-package type;
6. `java.lang`;
7. exactly one sealed wildcard-import match;
8. fully-qualified existing type, otherwise `UNRESOLVED`/`AMBIGUOUS`.

Every parameter and return type stores the complete resolution receipt plus its
hash. The type-universe and aggregate resolution-receipt hashes enter the trust
closure. Array dimensions are applied once. Javac agreement was 300/300 for
supported targets; foreign-unimported, missing explicit import, missing FQN,
wildcard ambiguity, and varargs descriptor errors were all 0.

## Independent truth and seal

The oracle is `tools/m342_java_oracle/JavaSemanticOracle.java`, a standalone
JDK compiler API helper using `ToolProvider`, `JavacTask`, `Trees`, `Types`, and
`Elements` with `--release 21 -proc:none`. It imports neither Tree-sitter nor
production acquisition code. Oracle SHA-256:
`783270b924ba6fa0b41c2741ef63f568ed5eea0fe4fb0d054c37164d3c2cda63`.

The compiler parse phase sealed 600 physical coordinates before semantic
classification. Compiler analysis then labelled 300 supported positives and
300 withheld semantic negatives. No unresolved row was dropped from a
denominator.

- Target census: `50b73f75ac4eea6d78fb72dd749cb1b911a1ba22c58fc4f35f86429d9ee55daa`
- Golden manifest: `277efdda22b2a3572e07286ce2395f666f45e5155b112cd66f670acacf48e4aa`
- External seal: `d9a26bc5803e395611e6bb5db579f27cf03f5c84b5aa78073bb6e3827d9708ad`

The immutable evaluation configuration rejected a rehashed golden manifest,
post-proposal phase, other source closure, and changed census. All four
forgeries were rejected.

## Evidence policy denominator

The checked-in independent policy classifies every required field before any
receipt is generated. Its manifest hash is
`ff1b029f8587c262b057b4b1dafa589633e8c69c680093cde9280e55d13956bf`.

| Field inventory | Classification |
|---|---|
| `content.subject_type` | `FIXED_SCHEMA_METADATA` |
| `content.predicate_id` | `DIRECT_SOURCE` |
| `content.object_type` | `FIXED_SCHEMA_METADATA` |
| `content.qualifier_ids` | `FIXED_SCHEMA_METADATA` |
| `content.receiver_type` | `DETERMINISTIC_DERIVATION` |
| every parameter name and source type | `DIRECT_SOURCE` |
| method return type | `DIRECT_SOURCE` |
| constructor `return_type="void"` | `DETERMINISTIC_DERIVATION` |
| every generic constraint | `DETERMINISTIC_DERIVATION` |
| `preconditions`, `postconditions` | `FIXED_SCHEMA_METADATA` |
| every declared exception | `DIRECT_SOURCE` |
| `deprecated_since`, `examples` when absent | `NOT_APPLICABLE` |
| proposed kind, epistemic character, extraction method | `FIXED_SCHEMA_METADATA` |
| status authority, ambiguity fields | `DETERMINISTIC_DERIVATION` |
| source-segment and parser-node binding | `DETERMINISTIC_DERIVATION` |

Measured evidence counts were required/present/exact =
12,598/12,598/12,598; missing/extra/duplicate/wrong = 0/0/0/0;
completeness/exactness = 1.000000/1.000000. The constructor return receipt count
was 1. Disabling return receipts left the denominator unchanged, produced 600
missing fields, and reduced affected trust to zero.

## Count-first evaluation

| Evaluation | Raw counts | Calculated ratios |
|---|---|---|
| Proposal extraction | TP 600, FP 0, FN 0 | P 1.000000, R 1.000000 |
| Exact source location | exact TP 600, wrong FP 0, missing FN 0 | P 1.000000, R 1.000000 |
| Automatic trust | correct trusted 300, wrong trusted 0, correct withheld 300, incorrect withheld 0 | P 1.000000, R 1.000000, coverage 1.000000 |
| Safe abstention | expected 300, correctly withheld 300, wrongly trusted 0 | 1.000000 |
| Seeded conflicts | expected/detected 2/2, missed/spurious 0/0 | P 1.000000, R 1.000000 |

Meta-regressions recalculated, rather than overrode, their outputs: one missing
proposal lowered recall to 0.998333; one spurious proposal lowered precision to
0.998336; one wrong trusted target lowered trust precision to 0.996678; one
missed conflict produced recall 0.000000; zero trust produced coverage
0.000000 and precision `N/A`.

## Review authority, parser bytes, duplicates, and replay

Only full batch verification issues an in-process
`VerifiedJavaTrustAuthorization` capability. Authentic authorization was
accepted. Unrehash mutation, rehashed decision, rehashed batch/closure, copied
proposal, other bundle, other seal, and withheld proposal were all rejected.

Tree-sitter runtime/package versions are 0.25.2/0.23.5, grammar ABI is 14,
common source artifact SHA-256 is
`f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38`,
and common verified manifest is
`1b31bf144f5c22e9c2b59bac5aad3b4637176da18b929533aeb5d28ac7ea516b`.
The platform-specific artifact verification passed on both systems. Windows used
locked wheel `1ee45e790f8d31d416bc84a09dac2e2c6bc343e89b8a2e1d550513498eedfde7`,
installed payload `adfeb93a538e6901b934468be726993a6481a2f56e85459761ca888ebc83c861`,
and platform manifest
`bf9ddcc8bc6e34738fb0a41358aff2a567dbaeff504793b36b358f7b8eaede2f`.
Karina Linux x86_64 used locked wheel
`370b204b9500b847f6d0c5ad584045831cee69e9a3e4d878535d39e4a7e4c4f1`,
installed payload `dc8ce23b2a711ff446226f49eca7dff97c935f58ea8915fe70008656a7c0a684`,
native binding `766dcdc998aaccd38fe8fe34a2eeb795768231e2df9ef00d429181e3120995c3`,
and platform manifest
`d8b79908b5d42012a44ad370d36622065f9f4228cf4d3274a7a71600437c4bfa`.

Physical duplicate rate after canonicalization was 0.000000; lexical
repetitions remained separately measured as 1; calculated
duplicate-derived trusted proposals were 0. Multi-alias multiplicity is counted,
not collapsed to presence/absence.

The compiled pack binds a content-addressed replay artifact. A fresh Python
process reloaded nine immutable source blobs and independently reran the full
pipeline: 300 trusted authorizations and 12,598 evidence receipts, PASS. Eleven
re-bound mutations (source bytes, receipt, field path, span, derivation,
semantic identity, proposal, seal, policy, decision, and pack source binding)
were all rejected. Pack hash:
`33f913f91bbaa5ac536cd15f2911a21c7a5b74dae324662e4e2d15deaab76cf4`.

## Measured side effects

Acceptance ran under a socket guard and recorded the exact allowed standalone
Python verifier commands. Measured socket attempts, Java source executions,
annotation-processor invocations, FactMemory writes, RuleMemory writes, and
registry mutations were all 0. PyTorch was absent before and after the run.

## Platform gates

- Windows Ruff: PASS.
- Windows targeted tests: 18 passed.
- Windows full suite at implementation SHA: 840 passed in 1118.43s.
- Windows measured acceptance and standalone replay: PASS.
- Karina (`192.168.100.6`) detached exact implementation SHA and clean worktree:
  PASS.
- Karina Ruff: PASS.
- Karina targeted tests: 18 passed in 22.65s.
- Karina full suite: 840 passed in 292.88s.
- Karina measured acceptance, Linux parser-artifact verification, and standalone
  replay: PASS.
- Machine comparison of all 14 required platform-independent hashes: 0
  differences.

| Cross-platform artifact | Identical SHA-256 |
|---|---|
| compiled pack | `33f913f91bbaa5ac536cd15f2911a21c7a5b74dae324662e4e2d15deaab76cf4` |
| conflict confusion | `ad098c457d22672cb50cf84edd2e583708109d1ebc74f8473027a709f5bdab6d` |
| evidence manifest | `cbc7c16bcbab2e57f514184d3b3d46a776721ab203526fb0aac813a8d1facf26` |
| evidence policy | `ff1b029f8587c262b057b4b1dafa589633e8c69c680093cde9280e55d13956bf` |
| golden manifest | `277efdda22b2a3572e07286ce2395f666f45e5155b112cd66f670acacf48e4aa` |
| golden seal | `d9a26bc5803e395611e6bb5db579f27cf03f5c84b5aa78073bb6e3827d9708ad` |
| parser common artifact | `1b31bf144f5c22e9c2b59bac5aad3b4637176da18b929533aeb5d28ac7ea516b` |
| proposal confusion | `9a5c5d4ccafa33d59c11dd14acee7f218ca30dec4328c3e63cc60dd948214eec` |
| source-location confusion | `c90a7e67a8c1c35b480678483054ef72ee28e66100dfea992f383fdf086d3872` |
| standalone report | `02b0dc8aa7b287196acfece5cf112f1313a6608256d6323a62f039576d0a5658` |
| target census | `50b73f75ac4eea6d78fb72dd749cb1b911a1ba22c58fc4f35f86429d9ee55daa` |
| trust closure | `f8d2d5226354315e7ebf77bb8497708c52dfb24596dd13ce5700c6aa2551d0eb` |
| trust confusion | `d5b251e32f3100900f8b8638ecb14cf72123fb4ce7d6825353adb8acd8b06470` |
| type-universe manifest | `3cf51a2244ee3d8a7dbba964d55522f248e3ed7902fdbb368bae72989327a90f` |

The authoritative machine-readable reports are
`runs/m342_pre_freeze_integrity/windows/acceptance_report.json` and
`runs/m342_pre_freeze_integrity/karina/acceptance_report.json`. The untouched
frozen evaluation remains unexecuted.

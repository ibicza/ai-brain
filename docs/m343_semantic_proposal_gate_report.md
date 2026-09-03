# M-34.3 semantic proposal truth and executable pre-freeze gate

## Release boundary and decision

- Branch: `exp/stage3-m343-semantic-proposal-gate`
- Exact base: `ed8cae0a8ad9d36530ae23ce9e07aae2615a9f48`
- Implementation commit: `981c25a4deb3998cd46963e4c0f315f0140d8d4c`
- Evidence commit: this evidence-only commit; its SHA is reported by the release handoff.
- Untouched/final evaluation executed: **no**.
- Derived development decision: **READY_FOR_FRESH_FREEZE**.

The implementation commit is the only implementation descendant of the exact
base. It contains no merge commit. M-33 Outcome C
`b94c17dc8b1026fe9e338b5fc0a4926b23d68a39` is not an ancestor. `gpt/`,
`policies/`, and `schemas/` have no diff from the exact base.

The production changes are confined to the Stage-3 Java acquisition and
Knowledge IR surfaces: `src/ai_brain/stage3/acquisition/` and
`src/ai_brain/stage3/knowledge_ir/{records,serialization,validation}.py`.
Harness, oracle, corpus, and regenerated compatibility fixtures live under
`scripts/`, `tools/m343_java_oracle/`, `tests/`, and `artifacts/`.

## Derived gate

`evaluate_pre_freeze_gate(raw_evidence)` constructs 70 typed mandatory
criteria. Each carries an ID, measured boolean or numerator/denominator,
threshold, status, and evidence hash. It calculates `READY_FOR_FRESH_FREEZE`
only when the number of failed mandatory criteria is zero; otherwise it
calculates `BLOCKED`. Loading a gate recomputes the complete report from raw
evidence, and any changed metric, status, decision, criteria hash, or report
hash is rejected. Mandatory ratio criteria reject an empty denominator.

The criteria cover corpus size and provenance (14), location/semantic/trust
truth (8), resolution (5), policy/evidence exactness (9), IR and overloads (3),
conflicts and duplicate safety (4), replay (3), process/side effects (8),
seal/parser/meta/platform integrity (4), quality (4), release facts (6), and
the prohibition on untouched evaluation (1). The authoritative bound gate is
70 PASS, 0 FAIL, decision `READY_FOR_FRESH_FREEZE`.

The acceptance script does not assign a READY result. Repository regression
tests reject direct assignments such as `decision = "READY_FOR_FRESH_FREEZE"`;
the only READY value in production is the enum branch selected by
`failed == 0`. A BLOCKED report causes non-zero acceptance exit, while READY
exits zero.

All 17 complete gate mutations recalculated a full gate and returned
`BLOCKED`: `wrong_trusted`, `missing_expected_proposal`, `spurious_proposal`,
`correct_location_wrong_content`, `wrong_source_location`,
`missing_field_requirement`, `extra_evidence_receipt`, `wrong_evidence_value`,
`missed_seeded_conflict`, `spurious_conflict`, `zero_trusted_proposals`,
`resolver_mismatch`, `unexpected_subprocess`, `socket_attempt`,
`changed_golden_seal`, `changed_parser_artifact`, and
`failed_standalone_replay`.

## Mixed corpus and independent truth

The development corpus contains 105 Java files: 50 byte-exact OpenJDK 25.0.2
source units from the pinned `java.base`, `java.compiler`, and `java.desktop`
module roots, plus 55 synthetic/support files. The source archive SHA-256 is
`658d6fe751ad9fc23d40a129654e2b26931209babf5ff7802273f3c468674e52`.
The corpus spans 18 packages and contains 1,733 callable targets: 1,233
supported positives and 500 semantic negatives; 125 overload groups (100
independently counted legal groups), 51 constructors, 175 generic methods, 25
intersection-bound methods, 150 throws declarations, and 25 nested-member
cases. It contains 50 duplicate basenames, one CRLF file, one CR-only file,
one file without a final newline, and Unicode/LF cases. The intersection with
the prior M-33/M-34.1/M-34.2 source hashes is zero.

- Corpus manifest: `1a390074bd170c741ee7997f90518bc989fab7e44e47ede3f0be8ba27719db10`
- Source manifest: `955b9dec3408610a3e019e87458f57a3f7ea476a0fed58b16b8f5960a203efbd`
- Target census: `ecd27b7fa34944160511cbede4b87c80b8450e6ae17d4790894cf7fc9b61b229`
- Golden manifest: `9a0e0b5c20f150fe88fd3af23b58ff18a171a8c57e0ee40d372385ee6be2f43a`
- Golden seal: `1a1bdf957f28d1511f176b9b800249da27ced5132b5b91070398b3f7b88e594a`

The independent oracle is
`tools/m343_java_oracle/JavaSemanticProposalOracle.java`, SHA-256
`f8f4c628515c4cd66cca6a670c1077b1205fb1e9678d96a2621e007ec848b0a7`.
It uses the JDK compiler API, `DiagnosticCollector`, `JavacTask`, `Trees`,
`Types`, and `Elements` with `-proc:none`; it imports neither production
acquisition code nor Tree-sitter. It emits sealed physical and semantic
identity, descriptor, parameter/return/bound/throws resolution, accessibility,
module export, diagnostic, expected-content, status, and blocker fields.

Non-zero normalized diagnostic counts were `COMPILER_ERROR=149`,
`UNRESOLVED_TYPE=266`, `INACCESSIBLE_TYPE=105`, and
`NON_EXPORTED_MODULE_PACKAGE=3`. The classifier also has deterministic
categories for ambiguous type, invalid import, invalid type-variable bound,
invalid throws type, duplicate signature, malformed generic declaration, and
invalid receiver/enclosing type; their measured counts were zero. Header and
semantic-identity errors block trust. Body-only compiler errors are retained
as receipts but do not block signature trust when they do not intersect the
declaration header.

## Raw proposal and trust measurements

| Matrix | Raw counts | Calculated ratios |
|---|---|---|
| Exact extraction/location | exact TP 1,733; wrong-location FP 0; missing FN 0 | precision 1.000000; recall 1.000000 |
| Exact semantic content | exact TP 1,733; semantic FP 0; missing FN 0; correct-location/wrong-content 0; spurious 0 | precision 1.000000; recall 1.000000 |
| Automatic trust | correct trusted 1,233; wrong trusted 0; correct withheld 500; incorrect withheld 0 | precision/recall/coverage 1.000000 |

The semantic comparator found no mismatches, so every per-field mismatch count
is zero (the serialized list is empty). Correct location with a changed
receiver, predicate, parameter name/source/resolved type, varargs dimensions,
return source/resolved/object type, bound, exception, epistemic character, or
status is a semantic false positive. `_golden_exact()` binds canonical source
signature, erased descriptor, expected semantic-content hash, resolution
manifest hash, and proposal-field manifest hash.

## Java IR and complete resolution

The existing immutable `ClaimSchemaContent` was extended with explicit Java
callable semantics. Mapping is: `void -> VOID`; `boolean -> BOOLEAN`;
`byte/short/int/long/char -> INTEGER`; `float/double -> DECIMAL`;
`String/CharSequence -> STRING`; enum, ordinary reference, array,
generic/type-variable, and wildcarded reference -> `ENTITY` while preserving
resolved Java identity and array dimensions. Unsupported/unresolved types are
not silently mapped to a trusted fallback. Constructors use callable kind
`CONSTRUCTOR`, predicate `<init>`, and an `ENTITY` result naming the constructed
receiver; their source return marker remains `void`, so they are not ordinary
void-returning methods.

All 1,733 declarations agreed with the independent resolution oracle.
Resolution receipts cover parameters, returns, every type-variable and
intersection-bound member, throws types, receiver/enclosing/nested owners, and
emitted annotation types. All 175 generic methods retained their bound data;
all 25 intersection cases retained every ordered bound; all 150 throws
declarations retained source and resolved exception identities. Measured
invalid-bound-to-Object fallback, unresolved throws accepted, inaccessible
types accepted, missing intersection bounds, and varargs descriptor errors
were each zero. Explicit unresolved bounds, inaccessible package-private or
private nested types, constructed local FQNs, non-exported platform packages,
and nonexistent static-import types were withheld.

## Executable evidence and conflicts

The evidence-policy manifest, SHA-256
`aa13eb29070e88169aeebdd44cd19a4087be4962f1424469f29c663830911ffd`,
is the sole classifier of evidence class, transformation, applicability, and
requirement. Dataclass introspection produced 63,762 concrete fields and every
field matched exactly one policy rule: unmatched 0, multiply matched 0,
unknown proposal fields 0, zero-match mandatory rules 0. The one zero-count
rule, `modifiers-empty`, is explicitly corpus-inapplicable. Constructor
predicate, return marker, callable kind, and object semantics use explicit
conditional rules rather than a fictional constructor field.

The pinned transformation registry hash is
`ea5afe93651ad79b7bf9215a59cdf675b63f58a17ffdad5d8c8d513ef219186a`.
Transforms execute from immutable source spans, indexed nodes, sealed symbol
receipts, or fixed schema constants; they do not copy `expected_output`.
Required/present/exact receipts were 63,762/63,762/63,762, with
missing/extra/duplicate/wrong = 0/0/0/0 and exactness 1.000000. Independent
oracle-field agreement was 44,384/44,384 (1.000000).

The exact seeded-conflict matrix had expected 2, detected 2, missed 0,
spurious 0, precision 1.000000, recall 1.000000. The exact kinds were
`DUPLICATE_PROPOSAL_BINDING` and `ONE_PROPOSAL_MULTIPLE_DECLARATIONS`, each
bound to its proposal/declaration/source-location instance IDs. All 125
overload groups passed indexing, proposal generation, trust/review,
compilation, and replay with zero legal-overload conflicts. Physical duplicate
count was 0/1,816 (rate 0.000000). The separately measured lexical repetition
count was 1,352/1,816 (rate 0.744493); it did not collapse physical identities.
Duplicate-derived trusted proposals were zero.

## Process audit and replay

The fail-closed audit observed 11 allowed subprocess invocations: one fresh
standalone replay, seven adversarial replay invocations, and three quality
commands. Each has an exact normalized argv policy, purpose, invocation count,
and receipt hash. Unexpected subprocesses, socket attempts, `os.system`
attempts, source executions, annotation-processor invocations, generated-class
executions, FactMemory writes, RuleMemory writes, and registry mutations were
all zero. PyTorch was not imported.

Standalone fresh-process replay preserved 105 raw blobs, 105 distinct
canonical-text entries, and 105 full relative paths, and reconstructed 1,233
trusted authorizations plus 63,762 evidence receipts: PASS. LF, CRLF, CR-only,
no-final-newline, Unicode, and duplicate-basename paths closed correctly.
Tampering with raw source, canonical text, semantic payload, evaluation config,
authority root, relative path, or evidence manifest was rejected (7/7).

The external configuration loader takes a caller-supplied path, expected file
SHA-256, and frozen authority-root hash; the path itself grants no authority.
The checked-in configuration file SHA-256 is
`0398a03920e8f1d5eb6b9e899a8009961adb5844e20ec93e1163da22f2481752`,
and its content hash is
`3eaa253c63a93665afa07f2e0c5eef10ab6e33d4db7ad51d26d18a6c4d62622a`.
The F13/H13/E13 verifier enforces allowed input-only and evidence-only path
transitions, rejects final source/golden hashes in F13 inputs, and rejects
production changes after F13. No F13/H13/E13 freeze was created or executed.

## Platform evidence

Karina at `ibicza@192.168.100.6` used a clean detached checkout at the exact
implementation SHA. Ruff, 26 targeted tests, the 866-test full suite,
acceptance, all mutations, and replay passed. Its complete gate was 70 PASS,
0 FAIL, `READY_FOR_FRESH_FREEZE`; report hash
`cc1a1493bddb9dd545ac0c803ac018cfb0a00ddfdcc0a72fbf6c168fb2a7bdad`.

Windows was run from a separate clean detached checkout at the same SHA with
the Karina peer report and verified release facts. Ruff, 26 targeted tests, the
866-test full suite, acceptance, all mutations, and replay passed. Its complete
gate was also 70 PASS, 0 FAIL, `READY_FOR_FRESH_FREEZE`; report hash
`b633b6582f993bdf6cd2c1485b46155926e041332fb71320c0c7bf3ae1f0ab8a`.
Both independently loaded gate envelopes recomputed to the identical gate hash
`cb14b5f569d32d3f0f2885272e019d93f256956a266484537527412c49ec0e21`.

All 18 platform-independent artifacts were compared byte-for-byte with zero
differences. Their shared
hashes are in `runs/m343_semantic_proposal_gate/cross_platform_hashes.json`;
the complete raw reports and independently reloadable gate envelopes are under
the per-platform directories.

The branch upstream matched the implementation SHA before the evidence commit,
both exact implementation worktrees were clean, the base-to-implementation
history had zero merge commits, and the local and Karina checks independently
proved M-33 outside ancestry. The evidence-only commit contains only this
document and `runs/m343_semantic_proposal_gate/`.

# M-34 blocker rework report

Status: PASS on the bounded development evaluation at implementation commit `1367404ca08a60bfb3ee341abe30be65ab38746c`.

## Release boundary

The branch `exp/stage3-m34-blocker-rework` starts from E11 `b55b61148d12386d6f2132b136b11f8dca859a7e` (H11 parent `af508a130b6e496f907254593387b13e4a73d2ce`). The M-33 branch `exp/stage3-cross-domain-blackbox` and its F12/H12/E12 commits were used only as failure evidence; none was merged or cherry-picked. Existing Stage-1 tags, `gpt`, and frozen/final artifacts were not changed.

The evaluation uses only the new fixtures under `tests/fixtures/m34_blocker`. It does not reuse the M-33 final frozen corpus as a development oracle and does not retroactively change Outcome C.

## Rework

- Canonical semantic identities now bind domain, immutable source document/snapshot, source unit, Java package and nested symbol path, member kind/name, erased JVM descriptor, exact line/byte span, normalized claim hash, evidence span hash, and a canonical identity hash.
- The bounded Java matcher reparses stored source bytes and requires exact symbol, signature, span, source-unit, evidence, and golden-location agreement. Similarity and proximity cannot grant trust. Missing golden locations, ambiguous/conflicting identities, wrong locations, duplicates, and incomplete evidence remain withheld with precise blocker categories.
- Java segmentation canonicalizes NFKC/whitespace-normalized segment hashes before proposal generation, retains immutable aliases, enforces exact duplicate rate `< 0.02`, and forbids duplicate-derived trusted proposals.
- Field-evidence reports include an exact per-domain denominator, ratio, missing field, source location, proposal, and failure category. Java incompleteness is a hard trust failure.
- Deterministic precompiler analysis detects identity/span, claim/identity, span/schema, symbol/signature, and duplicate-location conflicts before pack output.
- Trust follows only `candidate -> source_evidence_found -> identity_resolved -> golden_location_matched -> trusted`. Each edge has a deterministic receipt. Java defaults to `trusted_without_golden_allowed=false`.
- Java compilation requires a verified trust report and exact selected/trusted proposal closure. The safe-abstention regression proves that even a reviewed proposal cannot create a pack when it was withheld.

The Java parser is deliberately bounded. Java syntax outside its supported structural grammar fails closed through missing/ambiguous identity rather than being trusted heuristically.

## Development acceptance

The duplicate fixture begins with 4 exact duplicates out of 9 candidate segments (`0.444444`). Canonicalization produces 5 unique segments, 0 exact duplicates, and rate `0.000000`; duplicate-derived trusted proposals are 0.

Four Java trust scenarios produce 1 trusted, 3 withheld, and 0 rejected proposals. The only trusted proposal has exact semantic identity and golden source location. Wrong location is blocked as `untrusted_conflicting_identity`; missing golden location as `untrusted_golden_location_required`; incomplete field evidence as `untrusted_missing_field_evidence`. Java false automatic trust is 0 in all negative scenarios.

The incomplete-evidence fixture reports 9/10 (`0.900000`), identifies `synthetic.field.9` at source line 4 as `matcher_failure`, and forces trusted count to 0. The deterministic conflict regression reports `SAME_IDENTITY_DIFFERENT_SOURCE_SPANS`, fails before compilation, and creates no pack. The unresolved-identity safe-abstention case is 1/1 (`1.000000`) withheld and cannot compile or install an answer.

## Exact-SHA gates

Windows 11 / PowerShell:

- `uv run ruff format --check src scripts tests`: PASS, 442 files already formatted.
- `uv run ruff check src scripts tests`: PASS.
- `uv run pytest -q tests/test_m34_blocker_rework.py tests/test_m32_source_to_knowledge.py`: 26 passed in 48.75s.
- `uv run pytest -q`: 822 passed in 1047.20s.
- Acceptance executed twice: byte-identical, no CR bytes, exactly one terminal LF.

Karina / Linux, detached clean checkout of the same implementation SHA:

- `uv run ruff format --check src scripts tests`: PASS, 442 files already formatted.
- `uv run ruff check src scripts tests`: PASS.
- `uv run pytest -q tests/test_m34_blocker_rework.py tests/test_m32_source_to_knowledge.py`: 26 passed in 16.37s.
- `uv run pytest -q`: 822 passed in 270.10s.
- Acceptance executed twice: byte-identical; worktree clean after the run.

The complete Windows and Karina acceptance JSON files are byte-identical with SHA-256 `a4b7f206f243a730b49f146423e44f5cc7da2fc234f4857cabac1149d1183c82`. Cross-platform fingerprints are:

- source-receipt manifest: `46428bf978ba6a16b1f2cead349b3acf38532940ef86c764149b4834769d99ab`
- proposal identities: `b37e4577be2af12f21a528fdfae42aab2a0347fd33c59b7dc18f7186d57d7f7b`
- trust decisions/counts: `64d77acb3914d1d6677f967e1c6a83f72821f7868932e7c14944e2c09170c498`
- precompiler conflict report: `1802f49837ebf943870c99b6ac55fec947ee8b30e8302b96046cc77d81e3022b`

Runtime network is disabled and PyTorch is not loaded by the acceptance run. No persistence, backup/restore, or tutor saga path was changed, so their conditional gates are not applicable. No FactMemory/RuleMemory writes and no moral, moderation, refusal, political, ideological, NSFW, personality, or topic policy were introduced.

The refreshed local code graph contains 462 files, 6,138 nodes, and 59,837 edges in the parser report; the persistent graph contains 8,612 unique nodes and 85,650 edges.

## Decision

The M-34 blocker rework satisfies its bounded acceptance criteria. M-34 may proceed to a new untouched frozen evaluation through this fail-closed pipeline. This decision does not promote the M-33 Java proposals, reuse its final corpus as an oracle, or overturn M-33 Outcome C; any new ambiguity, evidence gap, duplicate conflict, or source-location disagreement must still withhold trust.

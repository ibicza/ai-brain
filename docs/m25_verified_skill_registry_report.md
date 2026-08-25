# M-25 Verified Skill Registry Report

## Decision

**Outcome A: safe skill routing works.** Stage 2 now has a separate checksummed SkillRegistry, perfect trusted structured/controlled retrieval, strong but assistive learned retrieval, explicit selection confirmation, and dispatch through the frozen Stage-1 executor.

## Boundary and Checks

- branch base: Stage-1 release code `4e9520a16bd3aeb7579ea92ce44060fd7f1a705a`
- release tag: `stage1-v1.0.1`; evidence commit excluded from branch base
- Stage-1 semantics changed: no
- local deterministic acceptance: PASS, 453 checks
- local M-25 tests: 24 passed
- trusted import without torch: PASS
- Karina M-25 tests: 24 passed; CUDA learned runs: PASS
- final full local/Karina gate and final commit SHA: recorded in release evidence after commit

## Catalog and Integrity

The catalog has exactly 89 unique active skills: NOOP 1, CLEAR 4, DRAIN 12, MERGE_TWO 24, MERGE_THREE 24, and DROP_THEN_TRANSFER 24. Aliases, descriptions, and 32,000 query examples are surfaces, not skills.

Registry persistence uses strict root/record schemas, mandatory checksum, validated atomic write, backup, and explicit recovery. Every record revalidates current RuleMemory, active verified status, semantic/specification/version binding, and installed receipt provenance. Lifecycle and tamper tests fail closed.

## Retrieval Results

| Route | top1/exact | top5 | Trust |
|---|---:|---:|---|
| structured specification | 89/89 | 1.0000 | trusted selector |
| semantic signature | 89/89 | 1.0000 | trusted selector |
| controlled RU/EN | 356/356 | 1.0000 | trusted selector |
| character n-gram development | 0.9925 | 1.0000 | assistive only |
| bi-encoder blind, 3-seed mean | 1.0000 | 1.0000 | assistive only |

Trusted RU/EN skill equality is 1.0000. Learned canonical RU/EN top1 equality is also 1.0000, but lower top5 ordering differs by language, reinforcing the review-only policy.

## Novelty and Safety

The learned blind unknown-abstention mean is 0.9662 with false-known mean 0.0338; all three seeds satisfy the research targets. Independently of those scores, wrong automatic skill selection, ambiguous auto-selection, unknown auto-selection, stale/deprecated selection, unrelated dispatch, and unconfirmed execution are all zero.

Selection receipts bind query/result/candidate/registry/memory/rule evidence and confirmation. Dispatch receipts rebind current registry, RuleMemory, InstalledRuleReceipt, state, limits, policy, and Stage-1 execution hash. Any changed artifact invalidates the operation.

## Dataset Discipline

The bilingual dataset contains 20k train, 2k validation, 2k calibration, 4k development, and 4k blind rows with complete contingency matrices and no prompt intersection. Model-visible text contains no IDs or split labels. Blind hashes were frozen before recipe selection and opened once after the three confirmed seeds were fixed.

## Scale and Limits

At 10,000 metadata/index entries over 89 unique skills, lexical index build was 1.32 s, query 8.90 ms, and peak memory 46.8 MB on Windows. The current trusted router favors full durable-store revalidation over low latency; a future immutable cached index may optimize this without weakening hash validation.

The learned result is strong within the generated controlled structural domain. It is not evidence for unrestricted natural-language understanding, new-rule acquisition, or safe neural execution. Stage 2 must continue to abstain or request exact confirmation outside this catalog.

## Recommendation

Adopt `SkillRegistry + exact trusted router + assistive character/bi-encoder candidates + explicit selection receipt + Stage-1 exact dispatch`. Proceed to factual memory while keeping free-text retrieval non-authoritative and retaining the frozen Stage-1 boundary.

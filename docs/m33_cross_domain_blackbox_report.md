# M-33 cross-domain black-box report

## Decision and exact boundaries

**Outcome C — false trust or black-box violation. Do not proceed to M-34 from
this branch.** The frozen independent evaluator found 832 Java proposals that
the production pipeline marked source-entailed but that did not match the
independent source-native golden location. The frozen ordinary compiler also
failed at the first final bundle with a conflicting semantic identity. The
installation barrier withheld every source proposal, so no wrong item reached
the tutor, but that does not erase the false automatic proposal trust.

- branch: `exp/stage3-cross-domain-blackbox`
- E11 baseline: `b55b61148d12386d6f2132b136b11f8dca859a7e`
- H11 parent: `af508a130b6e496f907254593387b13e4a73d2ce`
- F12: `ad3e35a36fcaafa267f3181b248c8269cb70287f`
- H12: `0608b8a0200cd930bff45eeb7950c953e246ede7`
- roadmap SHA-256: `8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`
- selector byte hash: `70b2143c475fb654d2ed4ff4c57cc9c6b3c5f02c922083f587ba3e63118d1bac`
- source-receipt manifest: `28c08bfd5d33aa8185b52d8de0fe06f622dd6d34792d7ba763c277ca7efc7ab1`

The F12-to-H12 freeze diff is `PASS` with zero changes to frozen code, schemas,
compiler/evaluator scripts, tests, provider/capability implementations,
`pyproject.toml`, or `uv.lock`. The verifier report hash is
`c769c82379581b96bbcaa28762017bb1a0fa3db020359eab4c7a1cd7be482c0c`.

## Real material and scale

| Bundle | Frozen identity/version | License | Docs | Words | Segments |
|---|---|---|---:|---:|---:|
| Kinematics | BCcampus College Physics, 2017-10-24 sitemap snapshot | CC BY 4.0 | 9 | 22,437 | 1,048 |
| Biology | Concepts of Biology 1st Canadian Edition, Chapter 3, 2021-03-04 sitemap snapshot | CC BY 4.0 | 6 | 13,231 | 447 |
| History | NPS Manzanar and US National Archives Japanese relocation pages, retrieved 2026-08-29 | US government public material | 2 | 3,528 | 169 |
| Java | OpenJDK `java.util`, JDK 21 GA commit `890adb6410dab4606a4f26a942aed02fb2f55387` | GPL-2.0 with Classpath Exception 2.0 | 8 | 55,087 | 10,660 |

The 25 immutable snapshots total 94,283 words and 12,299 non-document
segments. All 25 receipt hashes verify on Windows and Karina. The frozen
Library of Congress selector returned HTTP 403, so the history set uses the two
successfully sealed public-institution sources. OpenJDK was transported from
the exact tag using sparse Git after the frozen HTTP client timed out, then
normalized through the unchanged LF adapter.

The exact duplicate segment count is 5,818, a rate of 0.473047. This fails the
sealed 0.02 maximum. There is no generated filler, but line segmentation of Java
source counts repeated syntax and documentation boilerplate. The limit was not
changed or reinterpreted after source reveal.

## Independent evaluation

Goldens were authored by an assistive, non-human independent source-native audit
before production compiler output was opened. They do not import production
classifiers or extractors and are not represented as human approval. The frozen
evaluation result is `FAIL`, hash
`10f2f767c2327b8ab666e5c00b153bedebaa2d267ba5e50fc350684910cd6856`.

| Domain/kind | Proposals | P / R | Source-entailment P | Automatic-trust P | Wrong automatic | Field evidence |
|---|---:|---|---|---|---:|---|
| Kinematics / definition | 80 | 1.000000 / 0.930233 | 1.000000 | 1.000000 | 0 | 236/240, incomplete |
| Biology / definition | 24 | 1.000000 / 1.000000 | 1.000000 | 1.000000 | 0 | 72/72, complete |
| History / none | 0 | N/A / N/A | N/A | N/A | 0 | 0/0, complete |
| Java / claim schema | 883 | 0.000000 / 0.000000 | 0.000000 | 0.000000 | 832 | 4,944/4,995, incomplete |

Field precision is 0 for the nonempty final domains under exact independent
field matching; source-span exactness is `N/A` where there is no comparable
denominator. Conflict metrics are `N/A`: the goldens declared no exact conflict
instances. Capability metrics are `N/A` except Java, where precision and recall
are both 0. These values are calculated, not copied from fixture metadata, and
zero denominators remain `N/A`.

## Safe pack and runtime proof

After the frozen ordinary compilation failure, a data-only review artifact
withheld all proposals. Four empty content-addressed packs were compiled without
changing frozen code. Each executes and passes one mandatory abstention test;
none passes merely because records exist.

| Pack | Content hash | Evaluation |
|---|---|---|
| Kinematics | `c08960a64c3eaf21f84f9f684494dd391d2b2cc849b2f512b466e6e6c7effb68` | PASS 1/1 |
| Biology | `9593a66f3a055a139333f6ee7e2264c8b3b382e41072bdca4f9874a8da85cf52` | PASS 1/1 |
| History | `baad67117bf58b80dbd354f36b915872670bcbec42fe51bbb548e14571225e72` | PASS 1/1 |
| Java | `d206955b9695e7d1be87fc6abcda9c23092b05a560002bf2554329a6cd3bb51d` | PASS 1/1 |

The installed registry verifies four packs at
`fa2a09f3e1f827ac01016fef36a7f478a1f80b3e5989aa7625abcbfde2075c5d`.
Backup/restore reproduces the same registry and domains; report hash
`7ae15b3ab84cf8a76f52fbeba7343ebbe8f930a2623f9f5fea336d941683fe36`.

The held-out generator produced exactly 500 semantic keys—150 kinematics, 125
biology, 100 history, and 125 Java—with zero exact duplicates and zero reported
near-duplicate clusters. Every task deliberately expects conservative
abstention from the safe-withheld packs. Windows and Karina both returned
500/500 expected statuses, zero trusted answers, zero wrong trusted answers,
0.000000 trusted coverage, and 1.000000 abstention.

All queries traversed installed packs, the persistent educational service,
persistent conversation/progress stores, exact capability closure, and public
DTOs. The Windows run persisted 500 operations and 1,500 immutable stage
receipts with no recovery pending. The 14-point generic crash matrix and the
legacy M-30 recovery test passed in the full suite with one operation, three
stage receipts, and no duplicate authoritative event after recovery.

Moving final sources and goldens physically outside the workspace did not
change the 500 statuses (`PASS`, report hash
`309f32dbfebab01d8d4755f08a1e6996b7d15602e56654b164aaec04f78dd478`).
Socket-disabled runtime made zero network calls, did not load torch, and safely
returned `INSUFFICIENT_EVIDENCE` (report hash
`00ea2e4f99b8ac51730664f51b158d2b71a1e38168bc5fee7aaaa9205325c80f`).

## Exact-H12 gates and performance

Windows 10.0.26200 / Python 3.12.13 passed Ruff and all 834 tests in 1197.16s.
Karina / Python 3.12.14 passed Ruff and all 834 tests in 296.67s in the required
`m33-cross-domain-blackbox` tmux session. Both independently verified the
freeze, all 25 source hashes, and the same four-pack registry hash. Karina's
frozen compiler independently reproduced `ValueError: approved proposals
contain a conflicting semantic identity`; it therefore could not rebuild
segments, proposals, field evidence, packs, or installation artifacts to a
successful cross-platform hash comparison. This is a failed final gate and a
primary reason for Outcome C, not an omitted success claim.

Windows runtime performance over 500 persistent turns: p50 331,436,000 ns,
p95 386,053,300 ns, p99 419,330,600 ns, 3.061724 turns/s, peak traced memory
3,937,869 bytes. Karina: p50 120,009,663 ns, p95 140,908,542 ns, p99
144,001,475 ns, 8.215896 turns/s, peak 3,936,480 bytes. The Windows safe build
took approximately 14.4s wall time. Per-compilation-stage distributions are
unavailable because the frozen ordinary runner stopped at the first conflict;
they were not reconstructed after F12.

The exact-H12 graph is unchanged from the exact F12 graph: 467 parsed files,
6,171 syntax nodes, 60,787 edges; persistent post-processing reports 597 files,
9,238 nodes, and 86,590 edges. The pre-F12 baseline was 453 files, 6,023 nodes,
58,898 edges; persistent 583 files, 9,091 nodes, and 84,726 edges.

## Security, policy, and recommendation

The security result is `PASS_WITH_COVERAGE_LIMITATIONS`, hash
`619120ed5259a06ff49cca4dc1a88fe649b98c664a1a4726ca4d05222bf5b11b`.
Source-caused execution, self-approval, registry mutation, and FactMemory or
RuleMemory writes are all zero. Frozen synthetic security tests cover inert fake
approval/shell text, active-script stripping, off-seal URL rejection, and schema
mismatch. The real corpus itself did not contain every requested adversarial
category, so this is not reported as full corpus coverage.

No moral, moderation, NSFW, refusal, political, ideological, personality,
opinion, harmful-content, or topic policy was added. Abstention is epistemic and
capability-based only.

E12 contains only logs, calculated metrics, graph/freeze records, reproducibility
evidence, and final reports. Prior refs `gpt`, Stage-1 tags, H11, and E11 remain
unchanged. The branch is pushed without merge. M-34 should remain blocked until
a new development cycle fixes the generic semantic-identity/location contract,
complete field evidence, and segment deduplication using non-final development
material, followed by a new untouched real-material evaluation.

# M-33.5 Java determinism repair report

## Decision and source-control binding

Outcome: `READY_FOR_FRESH_JAVA_FREEZE`.

- Branch: `exp/stage3-m335-java-determinism-repair`.
- I14: `f738eaf1b4c710776c0cc37b13d8c07dac248158`, subject
  `M-33.5 canonical Java identity and determinism repair`.
- E14: the commit containing this report, subject
  `M-33.5 development readiness evidence`; its exact SHA cannot be embedded in
  its own content-addressed tree and is returned in the final task response.
- Parent chain: E14 -> I14 -> E13
  `f1599585c7b45e73eb3ba3cd9113155188eb6d26` -> H13
  `3f42cb044daadf29f9c1a1c69ca4706f15f8c75b` -> F13
  `af7657883fdb2c5ce47c3d82798ef7969b747c8c` -> pre-F13 base
  `f83a4b72de5843d699f971932b0dd28c872ab533`.
- M-33 Outcome-C `b94c17dc8b1026fe9e338b5fc0a4926b23d68a39`
  remains outside ancestry.

Roadmap SHA-256 is
`8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`.
M-33.5 repairs roadmap M-33. M-33.6 will perform the next fresh Java freeze;
M-33.7 will perform the final four-domain proof. Roadmap M-34 Episodic and
Relationship Memory has not started.

## Failure diagnosis and repaired identity

The six H13 compiler groups were completely classified:

| Groups | Classification | Members |
|---:|---|---|
| 2 | `CASEFOLD_COLLISION` | `MutableBoolean.<init>` and `setValue`: wrapper `Boolean` versus primitive `boolean` |
| 4 | `LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS` | `Validate.notEmpty` and `validIndex` families with distinct resolved erasures |

All 48 historical production conflicts were
`LEGAL_OVERLOAD_COLLAPSED_BY_UNRESOLVED_SENTINEL`; zero remain unclassified,
all implicated proposals were pre-trust withheld, none reached the pack, and
none was a true source/classpath conflict. The census hash is
`2c53c37c84b7a2b47eadb5b19d42b4223e62d6b47023a1d50fee9d534caab0d5`.

`JavaCanonicalCallableIdentity` schema 1 binds release hash, module or
`UNNAMED`, binary receiver, `METHOD`/`CONSTRUCTOR`, exact member or `<init>`,
ordered erased parameter descriptor, source/classpath scope and identity hash.
It is case-sensitive and independent of aliases, absolute roots, timestamps and
proposal ordinals. Return type and generic bounds remain semantic content;
varargs normalize to an array descriptor.

Legal overloads now compile as distinct authoritative records. Search aliases
are many-to-many and non-authoritative: an ambiguous short alias returns
`AMBIGUOUS_OVERLOAD` with sorted candidates, while an exact descriptor resolves
one record. Exact Knowledge IR references remain one-to-one and fail preflight
when unresolved or ambiguous.

## Packability, replay and runtime

- Proposals: 3,297; trusted: 2,688; packable: 2,688; withheld: 609.
- Legal overload groups: 321; true conflict groups: 0; post-trust conflicts: 0.
- Trusted packability coverage: 1.000000.
- Candidate pack hash:
  `4f4967cb616d8c9620fe3d9f21b988592d472ac9d3fd9ca6b1fc40742668c575`.
- Candidate pack tree hash:
  `4b312a08322a0e576efda15a6f80de69e5be007ce80c4d22c53b449dfab330b1`.
- Compile, standalone replay and isolated registry installation: PASS.
- Replay bound 2,688 authorizations, 240 raw blobs, 240 canonical blobs and
  127,547 evidence receipts without evaluator artifacts.
- All 11 required runtime-query categories passed, including explicit
  overload ambiguity and exact descriptor queries.

## Determinism and component roots

The old first observable divergence was `bundle_hash` (Windows
`1f99c27dedd59e1bcb4f715d858feb19701bb2e8741e32dc666f15d1081b400e`,
Karina `9bf49ef4dbbbe329d299f05d7394de6bac3a795a245c0ee40626d90a0d2fe556`).
Its first causal field was ordinal-bound `SourceDocument.document_id`: caller
and filesystem enumeration order associated different ordinals with equal
path/hash pairs.

After the fix both eight-case matrices pass with zero differences. Windows and
Karina agree byte-for-byte on all 11 comparator rows, including the full
candidate pack and component manifest; first divergent stage is `NONE`. The
cross-platform report hash is
`0dda209bc0bbd172a01fcfe8047c38b552d34a655473df1fbff79e3237eb9ed9`.

| Component | Root hash |
|---|---|
| Release identity | `fab13509521aba752a2e7a3f84cebfe98d718afa80c559f396f7c9f91a2613d5` |
| Source content manifest | `56e9c7e18a4c534c32d159acafae0659c546b27d376bfc98569fe4d0dead6d9e` |
| Bundle | `3efbf362a0a78bc6be65b20002ce6958a16bb6706ad802e6d2965721f42b8b55` |
| Documents | `8730a7cfe1cb3b5e3e33db2de8c580570a49a6ac89e2531a89d5c8b303b33576` |
| Type universe | `b285e66ff990b7114d6659989ee822c07c21a517fd80f295a6692e903cf27df0` |
| Source unit index | `3ae1043743d7f366f6996d400ec5a5abba6eca21511c36c374e1aa3853e4ba0e` |
| Declarations | `58fd3d80251c3aee81040d4c8a878c4abba94d0d3e2c5e05b21acc84e71ddda0` |
| Physical declarations | `e7b7242157a5ae4911bc25fd5e42dca7287e44da5c64f7249b71681c07f894f8` |
| Segmentation | `873f7e33869f2111d534b8d52945f721039fe5693d2ddc53d3adf982bbe59d24` |
| Proposals | `5f9e0ec327d452a05f83769a5c317ca12104991bcc07068c8edba439e2d8f30b` |
| Semantic identities | `27d26221793c6b7ec08f86e4ac8cc63b2fb4f1597d2c4e154a5feeaa267d94d0` |
| Evidence requirements | `394c8fa7e1806a00a311b833e4309863f98e9e2f013dd98e2d2b8518b78c79d7` |
| Evidence receipts | `f92df50a25f66b905b9be0040fb8d2f13b791ed2c0e77ac5e666653da3e8498f` |
| Conflicts | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| Packability | `4756fceb3b22c9fa31f0169705fac990da765ce1db29b112fcdc2836394f272d` |
| Decisions | `c130256c6d5fcfedd48e81c16cc0f983c5813caab7d439a15f8cafe70ff52fa5` |
| Trusted proposals | `6511b0f699d7dba7445a6758e02ab667063343b25ae872ce9bc3d18cb4211213` |
| Closure | `4cf32bf48fb67003d3a855531788ecf8d6ed2b753434f14b5b64051d40bc5d17` |
| Candidate pack | `f951922647815c4f8ede54deec868cde841bafc0cdcb5bb810915faef1244013` |

The component manifest hash is
`8d6d23261102c14adb16b46667a7db020afcb05e8312c8c8ab1c245269fbe5ad`.

## Development evaluation, freeze and quality

The disclosed-corpus evaluator measured location/semantic precision 1.000000,
recall 0.996976, trust precision 1.000000, trust coverage 0.897796, zero wrong
trusted, field-evidence exactness 1.000000 and resolution agreement 1.000000.

Role-aware historical freeze verification passed on both platforms with empty
protected overlap and hash
`c0876d864c8fc324671ac1812e796de59e7825f13cfa8141fbbce2f1cbe6f52b`.
The neutral audit-blob case passed and all 16 disclosure mutations were blocked.

The disclosed-corpus denylist binds 2 archives, 240 raw hashes, 240 canonical
hashes, 240 path/hash rows and 240 declaration manifests. Its source tree hash
is `a1da5983e0ab2ba64614d4e1bd69ada1953dfb3b86b8627dcfc317be89378192`
and manifest hash is
`f4d033a1eeff14a3d8b060c1c187859f4d6484c3ec21ff0469a88c56b3336435`.

Windows and Karina each passed Ruff, 79 targeted tests and the full 891-test
suite at exact I14. Both detached worktrees were clean. The branch and upstream
were equal before E14. Production made zero socket, unexpected subprocess,
source/class execution, annotation-processor or `os.system` attempts; it made
zero FactMemory, RuleMemory, SkillRegistry or pre-install provider/domain
registry writes, and did not import torch.

The V3 result is 51/51 mandatory criteria PASS and 51/51 gate mutations
blocked, report hash
`73c08508de6dc0a450724add934d61951f49ea08290f8d9846f10ecdffdcc0aa`.
E14 is restricted to measured documentation and `runs/m335_final_gate/**`;
the evidence-only allowlist is verified automatically before commit.

No new untouched corpus was acquired, selected, opened or evaluated. No moral,
moderation, refusal, political, ideological, NSFW, personality or topic policy
was added. The exact recommendation is to proceed to M-33.6 for a fresh,
untouched, oracle-free Java freeze; M-33.7 remains the subsequent four-domain
proof.

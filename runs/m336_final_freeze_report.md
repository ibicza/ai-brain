# M-33.6 final Java freeze report

Outcome: `OUTCOME_C`.

The exact pre-E15 chain is
`6b0c31e6e6f987216923a66e332370aeeffa9f48 -> d377a206bb251508b94680dd267f0c5cd02dd2aa -> ae86c630a4141dc97cfe97fd4a46d2eeaacc5831`.
E15 resolves from its Git object after commit; embedding a commit's own SHA in its
content would be circular.

Roadmap SHA-256:
`8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`.
M-33.6 is intended as the final Java freeze for roadmap M-33, but this attempt did
not close the Java blocker. M-33.7 remains required and blocked pending a successful
fresh Java freeze. Episodic and relationship memory have not started.

Phase 0 passed 23/23 criteria, blocked 23/23 gate mutations, and passed the complete
904-test suite on both platforms before F15. The F15 graph moved from 16,008 nodes,
111,642 edges, and 1,051 files to 16,027 nodes, 112,000 edges, and 1,051 files.

The one-shot selector was invoked exactly once and never rerun. Guava 33.4.8-jre
and Apache Commons Collections 4.5.0 carried verifiable Apache-2.0 text. Caffeine
3.2.0 archive
`67e14ef5c04c193a7fcafa788b55b89a079fd584b202469721ce6d2d6c753090`
had no license file recognized by the frozen archive policy. Selection stopped
before any final path or corpus existed. Production, evaluator, JDK invocation,
goldens, candidate pack, approval, installation, runtime proof, and final replay
were not run. Their metrics are `N/A / NOT_MEASURED`; mandatory empty denominators
fail.

At exact H15 Karina passed Ruff, 29 targeted tests, and all 904 tests. Windows passed
Ruff and 29 targeted tests, then reported 903 passed and one 120-second timeout in
the legacy chemistry CLI test. An isolated exact-H15 retry passed in 108.85 seconds;
the original full-suite failure remains recorded.

H15 changed only 18 allowlisted data/document paths and changed no frozen symbol or
implementation flow. The canonical role manifest covers all 18 paths, but the
frozen Git verifier compares JSON lists with Python tuples and reports mismatch.
The frozen disclosure derivation also reports nine predeclared metadata/path tokens
as F15 leaks. These post-F15 findings are not repaired in this branch, so freeze
integrity is `FAIL`.

No moral, moderation, NSFW, refusal, political, ideological, personality, or topic
policy was added. The next step is a bounded development repair of license
provenance plus role/disclosure serialization semantics, followed by a new freeze
and a new untouched corpus. Do not start M-33.7 until that Java freeze passes.

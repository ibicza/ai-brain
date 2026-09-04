# M-33.6b final Java freeze report

Outcome: `OUTCOME_C_BLOCKED`.

The exact pre-E17 chain is
`01fac1522c2cf694e440378b2bb58736ba4b9e28 -> cd5ffa4bdbc6ef40e702e3315515d87557e586c9 -> 1a05ccfa0bad25a79e388dab7c6672fc308cb890 -> E17`.
E17 resolves from the final Git object because embedding a commit's own SHA in
its content would be circular. The branch is
`exp/stage3-m336b-fresh-java-freeze-v2`; there are no merge commits and
historical Outcome-C commit
`b94c17dc8b1026fe9e338b5fc0a4926b23d68a39` remains outside ancestry.

Roadmap SHA-256:
`8d79042b74a7b474a7f6a94c41028ca80fd54b0e8d7f0c1879857fd77f4e8384`.
This run does not close the Java branch of M-33.

Phase 0 passed all 16 recomputed readiness criteria. Its disclosed-corpus
rehearsal used the production entry point, passed strict provenance replay and
real SCM verification, exercised all strong authenticity modes, gave unverified
signatures zero authority, enforced all 11 denylist identity classes, completed
1,122/1,122 mandatory disclosure claims with no missing/extra claims, and was
deterministic across Windows and Karina. F17 then froze the implementation,
schemas, policies, thresholds, candidate pool, orchestration, and protocol.

The project graph moved from 16,249 nodes / 115,007 edges / 1,075 files at E16 to
16,391 nodes / 116,758 edges / 1,090 files at exact F17. F17-to-H17 graph
analysis found 57 changed data/report paths, zero changed functions/classes,
zero affected flows, zero test gaps, and risk 0.00.

One global acquisition ran on Windows over the six frozen candidates. The sealed
38-file bundle tree is
`52e9f90c4d74dd3b2aa5104afb02917a261c9b1eed49ffb4e8cb8fcf23f8f7a0`.
Exact-H17 Windows and Karina verification found the same six canonical
provenance envelopes and zero platform-independent differences. All six
downloaded candidates were appended to the registry; its manifest is
`7cbac3b9ce45b697aea4f8be77b7fff9804c395d43631e4676eb9fa71ac3d68a`.
Pre-append overlap was zero in every one of 11 identity classes.

Qualification result:

| Candidate | Qualification | Authenticity | License evidence |
| --- | --- | --- | --- |
| Jackson Databind 2.20.0 | `ELIGIBLE` | `SHA256_SIDECAR_VERIFIED` | `EMBEDDED_EXACT_LICENSE` |
| Gson 2.13.2 | `REVIEW_REQUIRED` | `SHA256_SIDECAR_VERIFIED` | `POM_DECLARATION_ONLY` |
| HttpCore5 5.3.6 | `CONFLICT` | `IMMUTABLE_SCM_CONTENT_EQUIVALENCE` | `CONFLICTING_LICENSE_EVIDENCE` |
| Log4j API 2.25.2 | `CONFLICT` | `IMMUTABLE_SCM_CONTENT_EQUIVALENCE` | `CONFLICTING_LICENSE_EVIDENCE` |
| picocli 4.7.7 | `CONFLICT` | `MULTI_CHANNEL_VERIFIED` | `CONFLICTING_LICENSE_EVIDENCE` |
| Reactor Core 3.7.9 | `CONFLICT` | `MULTI_CHANNEL_VERIFIED` | `CONFLICTING_LICENSE_EVIDENCE` |

The complete qualification-set hash is
`fe7e32413d304243d8e7ead179f014ac90f88470233fc584165aadc272c723dc`.
Only one distinct eligible root existed against the frozen minimum of two.
The required stop rule therefore kept selector invocation/rerun at 0/0 and
production/evaluator at 0/0. Corpus, production, candidate-pack, replay,
semantic, trust, evidence, resolution, packability, wrong-trusted, installed
runtime, and performance metrics are `NOT_RUN` or `NOT_MEASURED`; no empty
denominator is called a pass.

Freeze/disclosure integrity also failed independently. The frozen H17 role
assembler rejects two paths emitted by its own production layout as unknown:
root-level `candidate_qualification_receipts.json` and
`sealed_acquisition_bundle.json`. A diagnostic over the remaining known paths
extracts all 10,179 required claims with zero missing claims, but finds 36 extra
protected fields. No role manifest can be truthfully committed, and the exact
freeze verifier therefore cannot complete. Frozen implementation is unchanged
after F17; these defects are recorded rather than repaired.

Exact-H17 Karina quality recorded 120 targeted tests, 995 full-suite tests,
no-torch/network and Ruff lint as passing. Its frozen quality wrapper reports
Ruff format FAIL because an empty changed-Python set expands to a repository-wide
format check and finds 11 pre-existing unformatted files. Windows exact-H17
recorded the same 120 targeted and 995 full-suite passes, plus no-torch/network
and Ruff lint passes; it reports the same Ruff format failure. The implementation
tree hash is byte-identical across platforms, and none of the 11 unformatted
paths changed in F17 or H17. The primary failed quality reports remain preserved.

E17 changes only evidence paths. No threshold or implementation changed after
F17. No moral, moderation, refusal, political, ideological, personality, or
topic policy was added.

M-33.7 recommendation: `BLOCKED_DO_NOT_START`. First perform a bounded
development repair for final role classification/schema closure and qualify a
new, undisclosed Java candidate pool with at least two eligible roots; then make
a new freeze and a new untouched acquisition.

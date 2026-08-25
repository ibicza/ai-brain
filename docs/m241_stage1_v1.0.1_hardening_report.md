# M-24.1 Stage-1 v1.0.1 Hardening Report

## Release status

Stage 1 v1.0.1 is frozen. Annotated tag `stage1-v1.0.1` resolves to exact tested release commit `4e9520a16bd3aeb7579ea92ce44060fd7f1a705a` and tree `0a45089cd8549d70596b55a6501591ef1504211f`.

Both complete gates passed on that commit. The local Windows gate and Karina Linux gate each ran dependency sync, ruff format/check, full pytest, M-24 acceptance, M-24.1 acceptance, the standalone RU UTF-8 workflow, audit reconstruction, RuleMemory recovery, and the no-torch trusted-path probe.

## Final gate results

| Gate | Local | Karina |
| --- | ---: | ---: |
| Full pytest | 452 passed | 452 passed |
| M-24 acceptance | 1267 checks | 1267 checks |
| M-24.1 acceptance | 81 checks | 81 checks |
| Standalone CLI | passed | passed |
| RuleMemory migration/recovery | passed | passed |
| Audit revision reconstruction | passed | passed |
| Proposal-ID collision isolation | passed | passed |
| No-torch import probe | passed | passed |

Local Python was 3.12.13. Karina used Python 3.14.4 at `/home/ibicza/ai-brain-m241-release` in tmux session `m241-v101-release`.

## Hardening delivered

- Every submission gets a unique opaque UUID-backed proposal ID; deterministic `original_input_hash` remains available for correlation.
- Every proposal workflow event carries a revision. Reconstruction preserves valid earlier revisions as `SUPERSEDED`, validates the active completed chain, and rejects stale or mixed artifacts.
- RuleMemory integrity, recovery, stored-rule parsing, and I/O failures have typed failure codes and expected failures are audited without catching programmer errors.
- Read-only backup fallback remains available, while writes from backup recovery state are blocked until explicit operator recovery.
- `recover-rule-memory` validates the backup, preserves exact corrupt primary bytes, atomically restores and validates the primary, emits evidence, and audits success or failure.
- Two legacy research tokenization tests now create isolated temporary tokenizers and therefore pass in a clean clone without ignored local artifacts.

## Failure loop

The first Karina run on H2 `1b823f53e77c69ae30fcd44372390f9a04d85766` found two clone-portability failures: M-19.2 tests depended on an ignored tokenizer artifact. No tag was created. H3 made those fixtures self-contained, then both complete gates were rerun on H3. H3 is H_FINAL.

## Evidence

- Local complete log: `runs/m241_release_evidence/local_exact_h2.log`
- Karina complete log: `runs/m241_release_evidence/karina_exact_h2.log`
- Evidence manifest: `runs/m241_release_evidence.json`
- Tag resolution: `runs/m241_release_evidence/tag_resolution.txt`

The historical filenames retain the protocol's prescribed `exact_h2` names; their headers prove they test H_FINAL after the required failure loop.

## Remaining limitations

The trusted frontend remains controlled RU/EN and strict form/DSL input, limited to the frozen four registers, three primitives, and six semantic families. Property verification remains scoped to Stage-1 semantics. RuleMemory recovery uses the designated validated backup and requires explicit operator action. Neural parsing and unrestricted natural language remain outside the trusted path.

Stage 2 should build on the frozen interfaces with a separately gated language-to-spec layer while keeping deterministic verification, approval, RuleMemory, and exact execution as the trust boundary.

# M-33.6b final trust metrics

Outcome: `OUTCOME_C_BLOCKED`.

The acquisition and provenance boundary behaved fail-closed: qualification
finished before any selection, the minimum-root failure stopped downstream
execution, and unverified signatures supplied no authority.

| Trust property | Result |
| --- | --- |
| Strict provenance-envelope replay | `PASS` for 6/6 |
| Immutable SCM receipt verification | `PASS` for 6/6 |
| Strong artifact authenticity mode | present for 6/6 |
| Unverified signature authority | 0 |
| Qualification set | `BLOCKED` |
| Eligible distinct roots | 1 of required 2 |
| Selector invocations / reruns | 0 / 0 |
| Production / evaluator runs | 0 / 0 |
| Prior-disclosure overlap | 0 in every one of 11 classes |
| Downloaded candidates appended to registry | 6/6 |
| Runtime trusted-process approval | `NOT_ISSUED` |
| Installed pack | `NOT_CREATED` |

The append-only registry is now the disclosure boundary for all six downloaded
candidates, independent of their qualification state. The registry manifest is
`7cbac3b9ce45b697aea4f8be77b7fff9804c395d43631e4676eb9fa71ac3d68a`.

Semantic trust metrics, replay mutation metrics, and installed-runtime trust
checks are `NOT_MEASURED` because the frozen stop rule prohibited their inputs
from being created.

# M-28.1 Source Refresh Report

## Baselines

| Authority | Publication | Version/date | SHA-256 |
|---|---|---|---|
| IUPAC | Periodic Table of the Elements | 4 May 2022 | `ef6ca2f6d46554f96e30ad3a60693d6630fe45ad81ce83cb14e508c6cbb7d3b3` |
| CIAAW | Standard Atomic Weights | 2024, 23 Oct 2024 | `b48282594b1fb01eee3cbc9d469ce5e3483b628157ea1b09ede33e3476895cf2` |
| CIAAW | Abridged Standard Atomic Weights | 2024, 23 Oct 2024 | `f9e9554471749c55a624aec55151922470a7f4104c62811eb194fed9731b907d` |
| BIPM | SI Brochure, 9th edition | 4.01, 4 Jun 2026 | `1122cf38e25b23d780a30607c68f7350b2b6d1f9970a89947aaa87a45ecbb20a` |

BIPM DOI: `10.59161/AUEZ1291`. Official URLs and retrieval metadata are stored
in `sources/source_chain.json`. The project-local reviewed Russian-name policy
has SHA-256 `d36cd295cf9a2d0cf5f11013954cc0ddea154e5f6456afcc0c27d1162b5ec4b0`.

## Refresh Policy

Acquisition accepts HTTPS from the allowlisted official hosts, applies response
size limits, and requires exact pinned hashes. Runtime is offline. A changed
official publication is a new reviewed source/version and requires derivation
and domain rebuild; it never mutates an existing record.

Full offline re-verification requires the bundled source cache. Reacquisition
requires network access and is a release-maintenance action, not runtime behavior.

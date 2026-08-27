# M-28.1 Source Derivation Chain

The chain is `official snapshot -> deterministic extractor -> derived extract ->
reviewed evidence -> claim`. All links are content addressed.

| Derived extract | SHA-256 | Derivation hash |
|---|---|---|
| IUPAC selected identities | `e567a2c734142834a1f9f84583f66e50e3c4907b39cdb7996213179be1dafe7c` | `935739ffbe051b6a8840a22942356dffc68e52eff4d04c2fe0d398091371ae83` |
| CIAAW selected weights | `fe7cb4746b0b8d121732978e5a89ca217b1d5da22b39596de4aaed311562bacc` | `d63b7f72c56765b1dba2e6f561fbbd6d89dd5dd596f92b0cf4038520f13c4ee8` |
| BIPM mole constants | `4bba50fd7013ff5f7667091d3a21b3945345243f5846aa7151678cd196c8b605` | `2404b354d9a43d730aa4e95d17eb128f7a70fd726f179b4759fcbd8929557cc1` |
| Reviewed RU names | `f7137ce29752f1cf24fcfce1d3c93d2c5bcbda070da13a8bf50808be3ca17d01` | `74e65379ac82eea167d4defb7406ca30a47bab3088fb4c639f3444f67b866a5d` |

The verified aggregate chain hash is
`ea5ae3c9c9c7283e26e22a2dfb2ef17047d4249d3117b525601296ab6edce87f`.
Verification checks source, output, extractor implementation, and derivation
record hashes. JSON derivation output uses explicit LF newlines so byte hashes
are identical on Windows and Linux. An implementation change requires a new
derivation.

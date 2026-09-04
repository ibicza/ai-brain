# M-33.6b source correspondence v2

The correspondence model distinguishes raw same-path equality, canonical-text same-path equality, relocated raw equality, relocated canonical equality, verified generated provenance, unmatched entries, and ambiguous matches.

Raw, canonical-only, relocated-raw, relocated-canonical, generated, unmatched, and ambiguous counters are recomputed from entries. Canonical-only matches bind the exact newline/BOM/NFC normalization receipt. Automatic SCM content equivalence accepts the first five classes only and requires a nonempty denominator with zero unmatched and zero ambiguous entries.

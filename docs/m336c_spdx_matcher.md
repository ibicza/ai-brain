# M-33.6c deterministic SPDX matcher

`SPDXLicenseMatcher` reads the frozen XML snapshot and emits a hash-bound `SPDXLicenseMatchReceipt`. Automatic authority is limited to `EXACT_BYTES_MATCH`, `EXACT_NORMALIZED_MATCH` and `SPDX_TEMPLATE_MATCH`. Multiple, near, absent and malformed matches never become automatic identities.

The interpreter handles template optional sections, replacement spans, case, HTTP/HTTPS normalization, whitespace, line endings, permitted punctuation and bullets. Cheap lexical prefilters only reject impossible matches; they cannot grant a match. There is no embedding, edit-distance threshold, substring-only authority or LLM classification.

The independent source-derived corpus contains 500 valid Apache variants, 500 substantive mutations and 500 controls. Result: 504 correct automatic identities, precision 1.000000, false automatic matches 0, false Apache matches 0, optional Apache variants rejected 0, and substantive mutations blocked 500/500.

# License evidence model

The frozen normalizer requires strict UTF-8, removes a BOM, normalizes NFC and newlines, strips trailing horizontal whitespace per line, and emits one terminal LF. Apache-2.0 is recognized only by equality with canonical SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`; the old `b"Apache License"` substring test is gone.

`EMBEDDED_EXACT_LICENSE` and complete `POM_PLUS_IMMUTABLE_SCM_LICENSE` can verify. Both agreeing produces `EMBEDDED_AND_SCM_CORROBORATED`. `POM_DECLARATION_ONLY` is `REVIEW_REQUIRED`; conflicting evidence is `CONFLICT`; no evidence is ineligible. Missing embedded text therefore does not mean incompatible licensing.

# M-33.6c license evidence fusion v2

Fusion consumes POM expressions, role-typed SPDX receipts and source correspondence. Matching recognized channels become `CORROBORATED` or `VERIFIED_EXTERNAL_CHAIN`. A POM-only declaration or an unrecognized project channel remains `REVIEW_REQUIRED`; it does not erase a valid embedded channel and does not become a conflict merely because its text hash differs.

`TRUE_LICENSE_CONFLICT` is reserved for incompatible recognized project-license expressions. Substantive additional restrictions remain review/conflict material. NOTICE and third-party documents are ignored by the project-license fusion denominator.

# M-33.6d SPDX expressions and scope

The parser represents license IDs, WITH exceptions, AND, OR and parentheses as typed nodes with deterministic canonical rendering. `GPL-2.0-only WITH Classpath-exception-2.0` remains distinct from plain GPL, and `Apache-2.0 OR MIT` is one valid alternative expression rather than a conflict.

Applicability is explicit at project root, module path, source-prefix or file override. The most-specific applicable scope wins. Two different resolved expressions are a conflict only at identical maximum specificity. Several POM license elements without a mechanically established relationship produce `REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE`.

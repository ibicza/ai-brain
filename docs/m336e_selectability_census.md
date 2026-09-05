# M-33.6e selectability census

Analysis eligibility and selectability are separate decisions. The disclosed
preflight re-runs authority, license, and SCM correspondence qualification, then
uses the exact production Tree-sitter index for every analysis-eligible root.
Every source entry receives a `SelectableSourceDecision`; ineligible roots remain
in the denominator with explicit blocker reasons and `NOT_RUN` parser status.

A selectable file must pass all ten frozen checks: candidate analysis eligibility,
derived/metrics publication, source-use receipt, scoped license, SCM
correspondence, parser, production declaration construction, callable kind,
production-supported callable, and declared evidence-policy path. The census does
not read goldens, evaluator output, trust metrics, or grant trust.

The sealed report carries separate denominators for analysis eligibility, parser
validity, callable files, production-supported files, selectable files, each root,
each construct, and each rejection reason.

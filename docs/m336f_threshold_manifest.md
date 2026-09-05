# M-33.6f acceptance thresholds

`M336FJavaAcceptanceThresholds` is the sole frozen source for M-33.6f Java acceptance values. Its manifest hash is `7f49b4a5112b2c5dcf5c7b6e95753e55c3099240b1209a11c810cb962156dfc9`.

Location and semantic precision are `1.000000`; location and semantic recall are `0.950000`; trust precision is `1.000000`; safe trust coverage is `0.850000`; field exactness and resolution agreement are `1.000000`; wrong trusted, post-trust pack failures, cross-platform semantic differences and fresh source leaks are zero.

All comparisons are derived from integer counts with `Decimal` or exact cross multiplication. The stale `0.800000` trust-coverage literal was removed from evaluator, pre-freeze, final-readiness and outcome paths. When wrong trusted is zero, trust recall, legacy coverage and safe coverage are asserted equal.

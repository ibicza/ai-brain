# M-29.1 genuine evaluation splits

The offline compiler persists DEVELOPMENT and FINAL_VALIDATION membership for eight axes: formula structure, element combination, numeric range, unit direction, template, RU/EN cross-language, multi-step composition and misconception holdout.

Membership is derived from actual immutable content, not a seed label. Every manifest stores exact semantic-key sets, intersection count and a manifest hash; catalog entries bind their applicable manifest.

All eight claimed intersections are zero. Their hashes are bound by `EducationalCatalogManifestV2` and verified at load time.

# Extraction methods

M-32 trusts `DETERMINISTIC_STRUCTURED`, conservatively handles `DETERMINISTIC_PATTERN`, and records `REVIEWED_MAPPING`. `ASSISTIVE_MODEL_PROPOSAL` is represented but always becomes `REVIEW_REQUIRED`.

Classification is driven by explicit source structure and content markers rather than domain tags. One generic classifier/extractor set handles kinematics, taxonomy, historical narrative, and Javadoc-like API material.

The deterministic extractor intentionally favors precision over recall. Unsupported syntax is skipped or becomes a technical abstention; no content or topic policy participates.

# M-33.6b qualification closure

The frozen pool contains unique coordinates, repository paths, and family identities. Each qualification decision binds the exact candidate coordinate and OPTIONAL requirement, a verified provenance envelope and semantic identity, status, reasons, eligible root, and decision hash.

The set verifier rejects missing, extra, duplicate, or reordered candidate identity; duplicate artifact bytes; duplicate root aliases; invalid decisions; substituted minima; and any receipt not independently reproduced. Required failures block. Optional failures remain explicit. Metrics, parser accuracy, evaluator output, and trust coverage are unavailable to qualification.

The selector may run once only after at least two distinct eligible roots exist, and its input is the exact sorted eligible-root set.

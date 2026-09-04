# M-33.6b disclosed-corpus rehearsal

The exact production coordinator is rehearsed on already disclosed Guava 33.4.8-jre, Commons Collections 4.5.0, and Caffeine 3.2.0. It uses the real Maven provider, POM parser, SCM ref/commit verifier, correspondence v2, provenance envelope v2, qualification closure, selector, registry loader, and disclosure schemas.

The sole difference is an explicit `DEVELOPMENT_DISCLOSED_REHEARSAL` denylist policy mode. It records every override and cannot be requested by final orchestration. No envelope field is changed by the override.

The gate requires three canonical envelope replays, complete SCM correspondence, the honest external-license result, no-sidecar eligibility through strong SCM equivalence, distinct roots, a single selector invocation, 11/11 identity-class denial, and Windows/Karina equality.

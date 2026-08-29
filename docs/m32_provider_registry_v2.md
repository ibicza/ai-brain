# Provider Registry v2

Provider authority is independent of capability descriptors. Each manifest binds provider ID/version/type, implementation bytes, helper bytes, resource policy bytes, input/output schema bytes, contexts, underlying authorities, status, and its own hash.

Capability resolution verifies the current provider manifest, strict semver range, recursive dependencies, receipt-per-dependency closure, DAG hash, schema compatibility, execution context, and authority monotonicity. Missing or incomplete closure yields `NEEDS_NEW_CAPABILITY`.

The reusable `generic.scalar_equation_solver.v1` depends on `generic.equation_validation.v1` and supports one bounded affine equality with exact rational arithmetic.

# Capability Registry

The checksummed registry stores immutable descriptors for reusable abilities,
not school subjects. A descriptor binds version, kind, RU/EN names, input/output
schema hashes, determinism, authority class, provider type and ID, exact provider
implementation hash, dependencies, contexts, resource policy, lifecycle status,
and descriptor hash. Dependency graphs are complete and acyclic.

Resolution is exact and version/context aware. A receipt binds requesting pack,
selected descriptor/provider, dependencies, authority, context, registry hash,
timestamp, schema, and its own hash. Unknown or incompatible requirements return
`NEEDS_NEW_CAPABILITY`; fuzzy/nearby selection is forbidden.

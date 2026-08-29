# Universal Knowledge IR 1.0

`ai_brain.stage3.knowledge_ir` defines 25 strict kinds and immutable records. Each
record binds a globally unique ID, domain, schema, epistemic character, existing
provenance references, dependencies, applicability references, required
capabilities, timestamp, typed content, and SHA-256 content hash. Content is a
closed union of text, relation, quantity, rule, procedure, and exercise-family
records rather than an arbitrary payload dictionary.

Canonical UTF-8 JSON round-trips are deterministic. Validation rejects wrong
schemas, hash changes, dangling/self dependencies, incompatible content tags,
unsafe executable epistemics, and malformed procedures. FactMemory remains the
factual authority; IR records only reference claims, evidence, sources,
derivations, and source-chain hashes.

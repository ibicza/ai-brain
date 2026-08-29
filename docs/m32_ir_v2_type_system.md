# Universal Knowledge IR v2 type system

IR v2 maps every one of the 25 `KnowledgeKind` tags to an explicit dataclass. Deserialization requires exact top-level and nested fields, rejects duplicate JSON keys and does not use a generic text fallback.

`ValueTypeRef`, `EntityTypeRef`, `QuantityTypeRef`, `DimensionVector`, `UnitRef`, and `VariableSymbolTable` provide reusable semantics. Validation covers declared/used symbols, scalar and quantity operators, equality and inequality compatibility, boolean operators, bounded powers, exact bounds, units, relation endpoints, claim schemas, capability references, procedures, cycles, targets, and epistemic authority.

Empirical, interpretive, and contested records remain descriptive; validation rejects their use as executable rule authority.

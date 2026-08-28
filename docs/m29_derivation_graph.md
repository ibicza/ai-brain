# M-29 Derivation Graph

`EducationalDerivationGraph` is immutable and content-addressed. It binds the source-result hash, chemistry/FactMemory/knowledge snapshots, source chain, formula AST, tool implementation, calculation and rounding policies, typed nodes/edges, root result, and provenance hashes.

Supported graph families cover paired fact answers, formula composition, molar mass, mass-to-moles, moles-to-mass, moles-to-entities/atoms, and entities-to-moles. Factual nodes carry claim, evidence, source, and derivation hashes. Rounding is represented as a display-only node.

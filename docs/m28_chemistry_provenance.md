# M-28 Chemistry Provenance

A ChemistryKnowledgeSnapshot binds the domain manifest, FactMemory snapshot, exact claims, evidence, active source records, source/calculation/grammar policies, selected element records, and Avogadro constant.

ChemistryResultBundle binds that snapshot, formula AST/composition, calculation steps, units, unrounded result, warnings, and policy versions. Results are saved in a content-addressed non-authoritative store. `provenance` verifies the artifact and returns replay status; it never promotes a result to a fact.

Replay distinguishes current, stale FactMemory/claim/evidence/source/manifest/policy/grammar/implementation, incompatible domain, and invalid result states.

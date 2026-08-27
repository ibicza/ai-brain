# Entity Amount Semantics

The entity tool requires an explicit basis:

- `FORMULA_ENTITIES`: amount times Avogadro constant;
- `TOTAL_ATOMS_IN_FORMULA`: additionally multiply by total atoms in the formula;
- `ATOMS_OF_ELEMENT_IN_FORMULA`: multiply by the target element count.

The canonical formula and composition are retained in the result and replay
binding. For example, 0.5 mol H2O is 0.5 N_A formula entities but 1.5 N_A total
atoms; 1 mol Ca(OH)2 is 5 N_A total atoms.

Total-atom and target-element requests require a formula. Negative quantities,
fractional entity counts for entities-to-amount, unsupported formulas, and stale
knowledge are rejected. “Molecule” versus “formula unit” is a requested display
label; the domain does not infer compound ontology.

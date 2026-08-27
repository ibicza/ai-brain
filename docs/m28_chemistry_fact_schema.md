# M-28 Chemistry Fact Schema

The pack contains 34 entities: 33 `chemical_element` entities and one `chemistry_constant` entity. Predicates are:

`element_symbol`, `element_name_ru`, `element_name_en`, `atomic_number`, `period`, `group`, `atomic_weight_kind`, `standard_atomic_weight`, `standard_atomic_weight_lower`, `standard_atomic_weight_upper`, `conventional_atomic_weight`, and `avogadro_constant`.

Values are typed FactValues. Decimal values never use float. The importer uses `STRUCTURED_JSON`, deterministic extraction, actor `TRUSTED_PROCESS`, identity `m28-curated-chemistry-import`, approved JSON-pointer evidence, review, approval, and commit. It performs no direct production SQL writes.

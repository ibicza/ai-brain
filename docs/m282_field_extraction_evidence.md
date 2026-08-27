# Field Extraction Evidence

Every production field carries `FieldExtractionEvidence` with canonical output value, upstream source and snapshot, locator type and locator payload, optional excerpt hash, extraction method, implementation hash, reviewer where required, and a content-derived evidence hash.

Coverage:

| Derivation | Method | Evidence form |
|---|---|---|
| CIAAW atomic weights | `DETERMINISTIC_EXTRACTION` | HTML table headers, rows, cells, notation, uncertainty |
| IUPAC selected identities | `REVIEWED_MANUAL_MAPPING` | Reviewed PDF table-cell locators |
| BIPM mole definition | `REVIEWED_MANUAL_MAPPING` | Reviewed PDF page/section locators |
| RU names | `POLICY_TRANSFORMATION` | Local JSON-pointer policy mappings |

The v3 chain contains 534 evidence records. Verification and acceptance report zero production fields without evidence. Changing a value, locator, method, implementation hash, or reviewer invalidates its evidence hash and derivation.

# M-28.1 Provenance Audit

Baseline audited: evidence commit `6948cb1fedd1babaf6a31f37ae72bfcc7cec042d`, implementation parent `6344bd2860ccc354196a41ab99895b4d59042859`.

The audit found one trusted-boundary gap: M-28.1 established reproducible source bytes, but a derived `SourceRecord` was not cryptographically tied to exactly one derivation and all of that derivation's upstream state.

| # | M-28.1 code path | Finding |
|---|---|---|
| 1 | `src/ai_brain/stage2/domains/chemistry/importer.py::_add_sources`; `source_derivation.py::build_source_chain` | Derived sources carried `derivation_hash` in license metadata only. |
| 2 | `knowledge_snapshot.py::_single_source_binding` | Snapshot construction checked derivation hash presence/count, not the complete record. |
| 3 | Same paths | No enforced equality between derivation `derived_extract_source_id` and current `SourceRecord.source_id`. |
| 4 | Same paths | No proof that derivation content hashes matched both current derived bytes and the FactMemory snapshot. |
| 5 | `source_update_v2.py`; `tests/test_m281_chemistry_integrity.py` | A source-update fixture could copy an old valid derivation hash to replacement metadata. |
| 6 | `models.py::KnowledgeBinding` | Full upstream source IDs, record hashes, snapshots, and states were absent. |
| 7 | `knowledge_snapshot.py`; `tool_registry.py` | Proposal creation did not resolve every required upstream source's current state. |
| 8 | `replay.py::replay_result` | Replay did not classify upstream retraction/unavailability independently. |
| 9 | `source_derivation.py::SELECTED_ELEMENTS` | IUPAC identity values came from a reviewed constant after PDF hash verification. |
| 10 | `source_derivation.py::AVOGADRO_CONSTANT` | The BIPM value was a fixed reviewed value after PDF hash verification. |
| 11 | `source_derivation.py::_extract_ciaaw_rows` | CIAAW values were genuinely parsed from frozen HTML tables. |
| 12 | `source_derivation.py::build_source_chain` | Local RU policy appeared inside `official_snapshots`. |
| 13 | `verify_source_chain` and M-28.1 reports | `official_count=5` conflated four authority downloads with one local policy. |

M-28.2 closes items 1-8 and 12-13 in trusted code. Items 9-10 are classified honestly as `REVIEWED_MANUAL_MAPPING`; item 11 remains `DETERMINISTIC_EXTRACTION`.

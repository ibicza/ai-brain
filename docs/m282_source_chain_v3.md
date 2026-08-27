# Source Chain V3

Source-chain version `3.0` separates authority snapshots, project policy, and project-created extracts.

| Category | Count | Contents |
|---|---:|---|
| `AUTHORITY_PUBLISHED_SNAPSHOT` | 4 | IUPAC periodic table, CIAAW standard, CIAAW abridged, BIPM SI Brochure 4.01 |
| `PROJECT_REVIEWED_LOCAL_POLICY` | 1 | RU element-name policy |
| Derived extracts | 4 | IUPAC identity, CIAAW weights, BIPM mole, RU names |

Derivation methods are one deterministic extraction, two reviewed manual mappings, and one policy transformation. The chain contains 534 verified field-evidence records.

`verify_source_chain()` checks file and canonical hashes, derivation hashes, one-to-one source mapping, implementation/policy hashes, upstream references, manual approvals, field evidence, category counts, and the outer chain hash.

Source-chain hash: `bb23631f47d927d4279d3744b735beec2f246e44c13b223f78d7f526a8dd898f`.

Trusted runtime uses bundled files only. Network access remains isolated to explicit build-time acquisition.

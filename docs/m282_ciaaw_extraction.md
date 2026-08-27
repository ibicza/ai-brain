# CIAAW Extraction

CIAAW atomic-weight data remains `DETERMINISTIC_EXTRACTION` from the two frozen official 2024 HTML tables: standard and abridged atomic weights.

Extraction verifies expected table headers, matches element identity, records row/cell locators, preserves source notation, keeps standard and abridged provenance distinct, and parses uncertainty/interval information. Every emitted field is linked to its upstream snapshot and an evidence hash.

The extractor implementation manifest and policy version are derivation inputs. Changing parser code, table locations, notation, uncertainty, or source bytes invalidates verification.

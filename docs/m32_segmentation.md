# Deterministic segmentation

Segments use the tags `DOCUMENT`, `SECTION`, `HEADING`, `PARAGRAPH`, `LIST`, `TABLE`, `DEFINITION_BLOCK`, `EQUATION_BLOCK`, `CODE_BLOCK`, `API_SIGNATURE`, `EXAMPLE_BLOCK`, `TEST_BLOCK`, `NOTE`, and `WARNING`.

Each segment binds byte and line ranges, heading path, optional table/page coordinates, exact source-span hash, and segment hash. Verification dereferences the original blob and hashes the selected bytes. The four fixtures produce 643 segments with 100% successful dereference.

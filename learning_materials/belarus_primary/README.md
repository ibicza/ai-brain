# Belarus primary-school source library

Russian-language grade 1-2 PDF originals supplied by the user on 2026-10-08.
This directory is the common project location for source materials, not a
finished model knowledge base or an automatically admitted training corpus.
All 13 originals were copied byte-identically from `D:\dwnld` (247,916,767 bytes,
1763 PDF pages). Removal of the download copies was blocked by the execution
tool; those copies remain. Do not describe this as a completed move.

- `originals/`: unchanged PDFs, explicitly archived in Git for noncommercial use.
- `manifest.json`: file identities, SHA-256, sizes, page counts, text-layer presence.
- `derived/`: renderings/extractions; disposable, not originals.
- `annotations_draft/`: proposed teaching examples, never automatically gold.
- `curriculum.md`: staged learning design and review boundaries.

## Source attribution and restrictions

[Источник: https://adu.by](https://adu.by/).
[Original electronic textbook catalog](https://e-padruchnik.adu.by/).
[Portal material-use conditions](https://adu.by/images/2024/04/03/Pravila-ispolzovaniya-informacii-portala.pdf).

The user authorized public noncommercial retention on 2026-10-08. All thirteen
supplied files were independently compared, byte-for-byte using SHA-256, against
the official downloads. Direct original URLs and catalog IDs are in `manifest.json`.
Portal conditions allow noncommercial use with source attribution and active
links, preserving existing links in the material. The textbook catalog separately
prohibits commercial/profit/advertising reproduction without rights-holder
permission and retains rights. This archive is for personal/noncommercial
research: it is **not** an open-license or public-domain declaration, permission
for commercial AI use, or a legal warranty. Commercial use requires a new rights
review/appropriate permission. The project's code license does not apply to PDFs.

No source PDF bytes or embedded links were rewritten. Rendering/text quality and
annotation admission are separate from publication permission. Future originals
remain ignored until individually reviewed; do not blindly force-add new books.
Publication metadata extends the schema-2 inventory to schema 3; the inventory
helper alone never approves rights or training. PDFs are still `NOT_ADMITTED`
to model training. Source URLs can change; retained bytes are identified by hashes.

Inventory is metadata only. Extractable text is not a substitute for seeing
pictures, layout, object ownership, crossed-out objects or inline pictograms.
Resource-image counts are not semantic object counts.
Parser warnings are recorded per PDF and page in inventory schema 2; incomplete
extraction must not silently become trusted training text. The inventory helper
uses `pypdf`; optional `fonttools` is needed for the supplied CFF fonts. This
session used pypdf 6.19.0 and fonttools 4.66.1. Neither extraction nor these
dependencies alter the originals.
The reviewed schema-2 inventory records a form-extraction limit warning in
`Rus_yaz_2kl_ch1_Guleckaya_rus_2022.pdf`. Also, only 56/118 pages of the first
grade-1 mathematics volume produced nonempty extracted text. Empty extraction
does not imply an empty page: visual rendering/OCR review is still required.

Before cutting examples, group parts/editions of the same work and recurring
illustrations into the same split family. Final held-out answers/annotations
must not enter training or retrieval used during training. Inspecting these
materials for curriculum design does not constitute an independent M33 blind
source nomination or close strict U.

Reproduce inventory into a fresh output path:

```powershell
.venv\Scripts\python.exe scripts\m33_textbook_inventory.py --originals learning_materials\belarus_primary\originals --output tmp\textbooks-manifest-check.json
```

Use the manifest hashes to verify every restored original. The first inventory
does not approve licensing, semantic quality, training readiness or broad
curriculum coverage.

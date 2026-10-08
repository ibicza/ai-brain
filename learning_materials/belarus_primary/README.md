# Belarus primary-school source library

Russian-language grade 1-2 PDF originals supplied by the user on 2026-10-08.
This directory is the common project location for source materials, not a
finished model knowledge base or an automatically admitted training corpus.
All 13 originals were copied byte-identically from `D:\dwnld` (247,916,767 bytes,
1763 PDF pages). Removal of the download copies was blocked by the execution
tool; those copies remain. Do not describe this as a completed move.

- `originals/`: unchanged PDFs, locally retained; temporarily Git-ignored.
- `manifest.json`: file identities, SHA-256, sizes, page counts, text-layer presence.
- `derived/`: renderings/extractions; disposable, not originals.
- `annotations_draft/`: proposed teaching examples, never automatically gold.
- `curriculum.md`: staged learning design and review boundaries.

The public `ibicza/ai-brain` repository must not be mistaken for private backup.
Full PDF publication is pending source-specific rights review and user choice of
backup destination. A manifest in Git alone does **not** back up the PDF bytes.
The textbooks retain their own rights; the project's code license does not apply
to them. Do not add the originals using `git add -f` without resolving this boundary.

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

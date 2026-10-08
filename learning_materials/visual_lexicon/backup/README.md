# Complete first corpus snapshot and recovery

Catalogue and corpus backups belong to the separate
`codex/belarus-primary-materials-catalog` branch of the existing project remote.
The application working tree/index must not be staged or switched to publish these
assets. A separate task-owned backup repository on D holds new archive objects.
Local W/D copies alone are not an off-machine backup; only a verified remote ref
confirms publication. The final chat reports the actual pushed commit separately.

Local first snapshot:
`D:\ai-brain-data\visual-lexicon\archives\20261009`.
Remote tree destination:
`learning_materials/visual_lexicon/backup/20261009`.

The corpus ZIP has 29,961 files / 774,897,383 source bytes, with no exclusions.
ZIP bytes: 553,580,232. SHA256:
`9866d4934b2cc8195775ec5ac38a252a219d8f3f2a89aa4a0af0fdd8a7bc02f7`.
Fourteen concatenated binary parts (not native multi-volume ZIPs) carry it; each
part is at most 40 MiB. `parts-manifest.json` gives their ordered paths, sizes and
hashes. `input-manifest.json` preserves relative paths, source hashes, timestamps
and roles. `archive-receipt.json` records complete ZIP and reconstructed-part
stream verification of every file. A full-sized duplicate `corpus.zip` is local
only, not uploaded along with its parts.

The snapshot includes draft labels, all page contexts, full PDF/OCR text and
coordinates, reviewed crops, labelled contexts, contact sheets, audits, plus
superseded historical resources. The latter are ARCHIVE_ONLY_SUPERSEDED and must
not be used instead of the correction-index effective view. All source files
were unchanged before/after archiving. Original PDF bytes are outside the derived
corpus root and are already preserved in this same archive branch under
`learning_materials/belarus_primary/originals`.

## Restore after a disk loss

Clone/download the archive branch into a new directory on a disk with enough
space. Do not check it out over a dirty application tree. Use the shipped helper:

```powershell
python scripts\lexicon_corpus_archive.py --restore learning_materials\visual_lexicon\backup\20261009\parts-manifest.json --destination D:\ai-brain-data\visual-lexicon\belarus-primary-20261009
```

It verifies part/ZIP/entry hashes and rejects unsafe paths, symbolic links,
case/Unicode collisions, or a nonempty destination. Restore to the original D
location if possible: workbook and OCR paths are absolute. Restoring elsewhere
requires an explicit, reviewed path remap in the catalogue and provenance records;
the helper does not silently reinterpret paths. Never delete the live corpus to
run a restore test. Full archive content was checked through a reconstructed
stream, not by overwriting the live directory; safe restore behavior was tested
with disposable fixtures.

Copy the current archived `visual_lexicon.xlsx` to the permanent editable catalogue
path. CSV/gzipped JSON are recovery/tool snapshots, not competing live authorities.
The before-books workbook is preserved separately as `initial-workbook.xlsx`.
Keep a new hash-named snapshot before subsequent edits.

Archive preservation is not semantic approval, an open licence, a training run or
model mastery. Source noncommercial restrictions still apply. Future backups
should append new assets/provenance incrementally instead of repeatedly adding a
second complete 528-MiB archive for small table edits.

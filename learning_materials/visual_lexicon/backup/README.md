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

## Second-pass additions

`backup/pass2-20261009/reviews/` preserves the supplemental page inventories,
annotations, generating helpers and review receipts. Restore this tree to
`D:\ai-brain-data\visual-lexicon\book-review-pass2-20261009` in a new/empty destination.
These records reuse first-snapshot effective page images; there is no second full
corpus ZIP. `annotations-before-pin-flag.json` preserves the exact earlier version
read by the non-blind cross-review; its receipt describes the one caution-note
addition rather than silently rewriting the reviewed bytes.

`backup/pass2-20261009/combined-prepared.json` contains the complete append-only
publication matrices and carries the earlier review/escape provenance. The QA
subdirectory preserves independent payload/XLSX checks and rendered sheet samples.
It excludes the redundant full inspection dump and transient runtime outputs.
The current canonical workbook and CSV/gzipped JSON exports remain at the stable
catalogue paths above, with old snapshots preserved by commit history and local
hash-named backups. Nothing in these archives admits data to model training.

## Word-sense additions

`backup/word-senses-20261009/` preserves the three reviewed lexical proposal files,
the morphology inventory, the append-only publication payload and independent
review receipts. Large JSON inputs are gzip-compressed; decompress them without
changing their JSON bytes. `backup-manifest.json` records both stored and original
hashes. The inventory helper is included for provenance, not as a training job.
The existing corpus and second-pass archives are reused, not duplicated.

Restore this addition to
`D:\ai-brain-data\visual-lexicon\word-senses-20261009` in a new destination. Its
`publication/prepared.json` references the unchanged earlier corpus/review roots;
restore those first. Canonical `sense_catalogue.json` and `word_review_queue.csv`
are at the stable catalogue location, alongside the workbook and other exports.
The authored examples are explicitly marked drafts, not quotations. Source-word
occurrence is not proof of every sense, an occurrence-level label, or model mastery.
No new media assignments or training metrics were added in this word-sense pass.

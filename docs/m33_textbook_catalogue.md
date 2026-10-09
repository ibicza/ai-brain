# Primary textbook catalogue: preparation, not training

The permanent editable file is
`learning_materials/visual_lexicon/visual_lexicon.xlsx`. Keep this path throughout
later milestones. `outputs/visual-lexicon-20261009/` is the older initial export,
not the editable current catalogue. Read current saved user rows before any
expansion; never replace them from a seed. Retain a hash-identified old snapshot.

## This first pass

Thirteen unchanged Russian-language Belarusian primary PDFs contain 1763 PDF
pages. Every page has an extraction record, rendered complete context and Windows
Russian OCR output, including picture-embedded text proposals. Native PDF text
is nonempty on 1659 pages; empty text-layer outputs are retained too. PDF text and OCR overlap; their
counts must not be added as unique occurrences. OCR can be wrong despite finishing
without technical errors. Tokenisation omits numbers/signs from the word-candidate
sheet, but keeps all original lines and OCR bounding boxes in linked source files.

The visual agents sampled 84 pages. They proposed 233 object/symbol/scene crops
and 122 additional concepts. Existing 338 concepts, descriptions, IDs, statuses,
percentages, model hashes and reports are preserved. Twenty-four supplemental
endpaper crops use printed labels, not independently demonstrated species
recognition; repeated endpapers are not independent examples. Thirty-one selected
crops received independent reading before comparison with the author proposal;
context viewed after comparison is explicitly distinct. This is not a blind model
exam or approval of every label. Detailed object-level review is still incomplete.

All 22,001 raster-placement crops are retained as raw placements, **not 22,001
recognised objects**. Complete page contexts retain vector drawings and scenes.
Thirteen CropBox/MediaBox mismatches required complete geometry-record replacement;
279 obsolete crops and 13 old previews are kept historically but excluded from the
effective catalogue. Three rejected raster placements are reported, not hidden;
their complete pages remain available.

## Complete page overview, second pass

Three agents actually viewed 153 contact sheets covering all 1763 pages, in three
disjoint book groups (560 mathematics, 690 world/art/reading, 513 language/safety).
Selected tiny or ambiguous images were rechecked at full-page resolution. The
overview inventories retain text-only, blank and unknown pages, not just positive
examples. Full-resolution viewing still does not mean every object was segmented.

The saved first expanded workbook was read before appending: 460 prior concepts,
all 27,523 media rows, all text rows and all coverage rows were preserved. The
second pass adds 387 proposed concepts and 5003 concept-to-page associations,
giving 847 concepts and 32,526 media/resource rows. Descriptions remain at most
20 words; no new measured percentages or training claims were introduced.
The original 338 user concepts and their results are still unchanged.

New whole-page relations mean "scene contains object" or "page contains symbol",
not isolated-object gold, verified localization, or proof of a numerical count.
Repeated hashes/roles/concepts are deduplicated; their original page evidence is
kept in annotation inventories and the export report. Unresolved names are kept
as review material instead of being promoted to confident labels. The first
84 detailed-review pages remain a separate coverage field: the overview must not
inflate that number. `review_queue.csv` has separate columns for these two levels.

A separate non-blind cross-review inspected 18 language/safety proposals on nine
full pages: 17 agreed, one tiny pin/needle scene was marked uncertain. Full-size
checks corrected several thumbnail guesses before publication. This sample is
not approval of all labels or a model evaluation.

Second-pass provenance is under
`D:\ai-brain-data\visual-lexicon\book-review-pass2-20261009`, outside the sealed first
corpus. Its inventories, annotations and receipts are included in the incremental
Git backup. Complete first corpus assets need not be uploaded a second time.

## Workbook sheets

- `Словарь`: stable concept/sense IDs, short draft descriptions, existing results;
  column N links proposed visual media without assigning train/test splits.
- `Медиа`: 32,526 resource or file-to-concept rows, paths, hashes, pages, coordinates,
  scenes and review caveats. Raw placement rows have no inferred concept ID.
- `Текст`: 15,499 candidate word/lemma records, original forms, separate PDF/OCR
  frequencies, possible concept matches, source contexts and uncertainty. Generic
  descriptions explicitly request semantic review, rather than invent meanings.
- `Покрытие`: per-book extraction/OCR/visual page counts and the validation boundary.

New labels remain user-pending. Blank metrics are not zeros or mastery scores.
Synthetic statuses were not promoted. All textbook resources remain unassigned and
unadmitted. No model weights, training, remote training service or M34 storage were
changed, and M33 closure is not claimed by this catalogue.

## Local storage and provenance

`D:\ai-brain-data\visual-lexicon\belarus-primary-20261009` holds permanent derived
assets, not temporary files. `books/<sha16>/records` links source bytes, 1-based PDF
pages, top-left PDF-point rectangles and image identities. Read
`geometry-corrections/replacement-index.json` as **whole-record replacement**, never
as a preview-only patch. The effective audit lists superseded files. OCR outputs
must match the effective page image hash. Text and scene occurrence does not prove
object identity, numerical counts or the intended sense of a homonym.

Review notes identify pictograms, anthropomorphic story objects, uncertain crops,
visible answer labels and repeated source scenes. They must survive future exports.
Never put related crops/pages, duplicated illustrations or labelled control images
into opposing training and evaluation splits. The reusable regression set will not
be a fresh blind final test after inspection.

Originals and their rights notices remain in `learning_materials/belarus_primary`.
Noncommercial source restrictions travel with derived files; this catalogue does
not assert an open licence or permission for commercial use.

## Reproduction and checks

`scripts/lexicon_textbooks_extract.py` preserves source text, boxes and pages;
`scripts/lexicon_windows_ocr.ps1` uses installed Windows OCR; the catalogue prepare
script reads existing saved workbook values without authoring Excel. The Node
updater imports the actual workbook and authors XLSX with `@oai/artifact-tool`.
`scripts/lexicon_catalogue_export.py` reads the saved XLSX, checks all exported cells
against prepared additions and writes CSV/gzipped JSON snapshots. CSV is UTF-8 BOM,
semicolon-separated and quotes multiline fields; leading formula-like strings are
escaped, typed numbers are not changed.

The initial-schema migration intentionally refuses added/reordered columns,
formulas or unexpected sheets rather than silently dropping user work. Future
expansions use `scripts/lexicon_catalogue_increment.py` on the actual four-sheet
workbook; do not rerun the initial migration on the expanded file. The
`--previous-prepared` option preserves earlier SHA-verified review metadata and
XML-display escape audits, while keeping saved user edits authoritative. It is
not a synchronisation daemon.

Rebuild the local code-review graph for navigation, but keep its cache out of Git.
Canonical catalogue backups must be isolated from unrelated dirty application
changes. See `learning_materials/visual_lexicon/backup/README.md` for the verified
archive and recovery boundary once the backup has finished.

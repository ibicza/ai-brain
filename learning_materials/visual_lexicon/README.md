# Visual lexicon: permanent project catalogue

Canonical editable workbook: `visual_lexicon.xlsx` in this directory. The earlier
`outputs/visual-lexicon-20261009/visual_lexicon.xlsx` is the initial export, not the
current catalogue. Do not regenerate the canonical workbook from that old seed.

The workbook owns user edits. Every expansion must first read its current saved
rows and preserve concept IDs, descriptions, aliases, statuses and measurements.
Write a hash-named backup before editing; refuse a changed input at publication.
Do not overwrite an open workbook or discard unsaved user edits.

`concepts.csv`, `media.csv`, `text_candidates.csv`, `coverage.csv` and
`catalogue.json.gz` are versioned exports for tools and
recovery, not competing editable copies. Regenerate them from the saved workbook
after edits. An exported CSV alone is not a synchronisation service.

Large extracted assets are kept together under
`D:\ai-brain-data\visual-lexicon\belarus-primary-20261009`, outside temporary
directories and outside the `.code-review-graph` cache. File identities, source
PDF hashes, pages and crop coordinates must accompany media links. Unchanged PDF
originals remain in `../belarus_primary/originals` and their separate Git archive.
Missing assets must be restored or regenerated and their hashes checked before use.

Additional page-overview inventories and proposed associations live under
`D:\ai-brain-data\visual-lexicon\book-review-pass2-20261009`. Their associations reuse
the hash-verified effective complete page images, not arbitrary thumbnail guesses.
An association means "this scene contains the concept", not a verified isolated
object or segmentation mask. `review_queue.csv` separates detailed crop review
from overview of a page. Both still require semantic/user approval.

Word occurrence is not visual identification. Automatic text forms/lemmas and
image placements are draft candidates. Ambiguous senses, extraction errors,
proposed labels and words visible inside illustrations require review. Existing
synthetic training statuses must not be upgraded because a word appears in a book.
No book media are admitted to training by catalogue creation. No training runs are
part of this task. All corpus split assignments remain unassigned until families
and recurring illustrations have been checked; a reusable regression suite is not
a fresh blind final exam.

Descriptions are limited to 20 whitespace-separated words. One stable ID identifies
one concept/sense, not every spelling. Preserve source word forms and contexts;
dictionary lemmatisation is a proposal, never a proof of the intended sense.

Initial saved workbook backup:
`D:\ai-brain-data\visual-lexicon\backups\visual_lexicon-before-books-20261009.xlsx`.
Backups and archive commits preserve older states; only the canonical workbook is
edited going forward. Local backups do not provide protection against loss of the
whole machine; report separately whether an off-machine Git backup was completed.

The original two-sheet migration is `scripts/lexicon_catalogue_prepare.py`.
Subsequent additions use `scripts/lexicon_catalogue_increment.py` on the actual
saved four-sheet workbook. It preserves existing rows, appends new rows, and only
extends existing unassigned-media links. Do not rerun the initial migration on the
expanded workbook. Both stages emit prepared JSON; `lexicon_catalogue_update.mjs`
imports the saved workbook and authors XLSX using the spreadsheet runtime.
`lexicon_catalogue_export.py` independently checks the saved cells and creates the
CSV/JSON exports. Publish only after input-SHA, export and visual QA checks pass.

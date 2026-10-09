# Visual lexicon: permanent project catalogue

The 2026-10-10 procedural continuation is documented in
`docs/m33_primary_composition_continuation.md`. Existing workbook rows/IDs remain
unchanged; result/replay/comparison JSON files preserve candidate outcomes
separately. Experimental capacity is not admission of animal-part recognition,
photographs, textbooks or general language.

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

## Lexical senses, 2026-10-09

`scripts/lexicon_word_senses_prepare.py` appends reviewed draft word senses to the
actual saved catalogue. Each new row has one explicitly scoped meaning, a stable
concept ID, a short description, and an authored example in column M. Inflected
source forms stay grouped on `Текст`; spelling matches never decide the sense.
Different senses of `есть`, `считать`, `мягкий`, `язык`, `лист`, `класс` and other
ambiguous words are separate records. Exact existing definitions can be reused
explicitly; neither fuzzy names nor aliases alone merge concept IDs.

This batch reviews 662 sense proposals: 647 new rows and 15 existing-ID mappings,
giving 1494 concepts. Existing 847 rows and all media/text/coverage values are
preserved. The new rows have no training/control files, model hashes or measured
percentages. Definitions/examples are lexical drafts, not independently verified
textbook assertions or evidence that the model understands a word. A source text
ID establishes spelling occurrence; it does not assign every occurrence to that
sense. Aspects/synonyms and additional meanings can be reviewed further in M34.

`sense_catalogue.json` keeps explicit lemma/sense keys, examples, source references
and their hashes for future use. `word_review_queue.csv` preserves all 15,499 raw
candidate records, with proposed IDs where reviewed and unresolved entries intact.
Unselected entries are not automatically judged invalid or merged into the main
dictionary. Training was not started or admitted by these additions.

## Compositional pilot vocabulary, 2026-10-09

The current catalogue additionally contains 27 explicit meanings for visual
attributes, visibility, animal anatomy and fruit parts: 1521 concepts total.
Existing 1494 concept rows and all previous media/text/coverage rows are preserved.
There are 45 new full-frame procedural image associations (32571 media rows total),
with exact source pixels, explicit left/right targets, split roles and hashes.
These are experimental training/regression resources, not isolated animal crops.

`composition_vocabulary.json` defines the additions and observation policy;
`composition_vocabulary_mapping.json` binds them to stable catalogue IDs.
Only dark green and the three pattern names participate in this procedural course.
Animal/fruit-part meanings are planned, not learned. Percentages remain blank:
the experimental course does not certify general understanding of those words.
Current weights are NOT production-admitted. See `docs/m33_primary_composition.md`
and `composition_result_v1.json` / `composition_result_v2.json` for the failures and
improvements. Numerical replay is separate from independent semantic/blind review.

Never replace observed anatomy with typical species anatomy: a hidden leg is
unknown, not missing or implicitly seen. Known final scenes are regression assets
now. These additions do not admit any previously unreviewed textbook media.

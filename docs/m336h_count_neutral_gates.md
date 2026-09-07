# M-33.6h count-neutral gates

The runtime-generated project-owned Java fixture targets 12 selected files, at least three roots, at most five files per root, and at least one closure-support file. It exercises real source-entry binding, closure construction and feasibility, one-shot M336F selection, native materialization, javac diagnostics, a withheld or compiler-blocked declaration, source-free pack verification, sealed replay, two platform seals, and independent evaluation.

The gate uses structural and threshold-derived assertions only. It explicitly requires its proposal, trusted, and withheld values to differ from the disclosed 1587/1575/12 tuple; replacement counts are not hard-coded into production success logic.

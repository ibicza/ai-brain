# M-33.6h canonical selection path

The only current final Java selection path is:

`SelectableSourceCensus` → `JavaCompilationClosureManifest` → `JavaCompilationClosureFeasibilityProof` → `select_compilation_closed_sources_once` → `M336FSelectedSourceManifest` + `M336FSelectorReceipt`.

`SourceEntryBindingManifest` is bound throughout. The exact strict M336F objects written by selection are passed to materialization and compiler-aware production; production binds them into replay and seal receipts. M336E `SelectedSourceManifest`, `SelectorReceipt`, and `select_final_sources_once` remain historical only. No M336E-to-M336F field-copy adapter exists.

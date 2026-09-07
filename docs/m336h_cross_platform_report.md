# M-33.6h cross-platform report

Windows and Karina executed exact R23 `c5f95cb1eaa20c055060cf00eb5f50a125e89fcc`. Registry `f2ebdc545fcc3de4b528977fc8739ec242352f0f61d5a9e6e5b6c4b735c74e17` and manifest `9000385a8c2863bbb9eb3fa8112abc7189d90dc3d8f02de7c4899544ba942f2c` were byte-identical. Selector policy, thresholds, selected manifests, candidate packs and semantic evaluation outputs had zero platform-neutral differences.

Two evaluator result hashes are classified as platform-private-derived because their requests bind private host paths. Excluding those allowed identities, all evaluator fields are equal. Public absolute paths, private roles and source leaks are zero.

# M-33.5 final-gate evidence scope

This directory contains exact-I14 quality logs, disclosed-development metrics,
complete packability reports, component-root manifests, replay/install/runtime
receipts, evaluator and side-effect reports, both eight-case matrix reports,
freeze/mutation reports, the cross-platform comparator and the derived V3 gate.

The comparator read the full production output, 38.9 MB component manifest and
complete candidate-pack tree from each platform. Their byte hashes and equality
results are bound in `cross_platform.json`; redundant opaque and installed
registry copies are not duplicated in Git. Temporary wrong-toolchain and
environment bootstrap attempts are excluded from final evidence.

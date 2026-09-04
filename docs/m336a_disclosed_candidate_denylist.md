# Disclosed candidate denylist

The accumulated loader combines M-33.5 with M-33.6a. The M-33.6a manifest has three coordinates, three source URLs, three archive hashes, three POM hashes, 1,024 raw Java hashes, 1,024 canonical Java hashes, three normalized SCM tree hashes, a path-manifest hash, 16,784 declaration fingerprints, three immutable commits, and three correspondence hashes.

It blocks exact/renamed/alternate-URL archive bytes, coordinate reuse even with changed bytes, newline-equivalent or relocated source content, and declaration-fingerprint reuse. Reacquisition is allowed only for an explicitly disclosed development regression. Manifest hash before final regeneration: `075a3d98bb6cd6c88f67e2444a0cd462e90f36c16e97f0b85b89698050ea5848`.

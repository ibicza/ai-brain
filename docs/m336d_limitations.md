# M-33.6d limitations

Four frozen defects block the requested final proof:

1. Five roots qualify for analysis, but the frozen callable-source filter leaves fewer than three selector roots; the one allowed invocation stops before selecting any file.
2. The frozen vault manifest and verifier disagree on path ordering, so both platform verifiers fail despite byte-identical physical vaults.
3. The frozen public contract rejects an unknown nested field in the acquisition report produced by the same pipeline.
4. The frozen M-33.6c regression asserts exactly six disclosure-registry entries and rejects the correct append-only H19 total of thirty.

Because F19 forbids implementation, schema, policy, selector, contract, threshold, and test changes, none can be repaired in H19/E19. Production and all downstream evaluation are absent. A new pre-freeze repair is required before attempting M-33.7.

# M-34.4 Git-derived freeze protocol

The verifier reads commits and blobs with Git (`rev-parse`, `cat-file`,
`rev-list`, `ls-tree`, and `merge-base`). Caller-created hash maps are not
release truth. It checks that F13, H13, and E13 exist, have exactly one parent,
form the exact base -> F13 -> H13 -> E13 chain, use the frozen commit subjects,
exclude the old M-33 Outcome-C commit from ancestry, and agree with branch and
upstream tips.

Paths are canonical POSIX relative paths. Absolute paths, backslashes, `..`,
duplicate normalized names, and frozen-scope symlinks are rejected. Prefix
membership is component-boundary safe, so `final-data-evil` cannot satisfy a
`final-data` rule. H13, E13, and frozen scopes are module constants; a caller
cannot weaken them.

After F13, frozen scope includes `src/**`, `scripts/**`, `tools/**`,
`schemas/**`, `tests/**`, `pyproject.toml`, `uv.lock`, and `.gitattributes`.
H13 is limited to the final Java evaluation tree and its three source-specific
reports. E13 is limited to exact-SHA reports and run evidence. The verifier also
proves final H13 blob identities were absent from F13 and all frozen blobs remain
unchanged through E13.

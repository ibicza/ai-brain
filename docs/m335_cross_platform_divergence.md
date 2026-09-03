# M-33.5 cross-platform divergence

The H13 Windows and Karina sets contained the same 240 path/raw-hash pairs and
the same canonical tree hash
`a1da5983e0ab2ba64614d4e1bd69ada1953dfb3b86b8627dcfc317be89378192`.

The first observable sealed field was `bundle_hash`: Windows
`1f99c27dedd59e1bcb4f715d858feb19701bb2e8741e32dc666f15d1081b400e`,
Karina `9bf49ef4dbbbe329d299f05d7394de6bac3a795a245c0ee40626d90a0d2fe556`.
The first causal field was `SourceDocument.document_id`: the v1 ID contained a
caller-order ordinal. Different filesystem enumeration associated different
ordinals with the same relative paths. That changed document, bundle, segment,
proposal, evidence, decision and closure identities. Candidate row 0 consequently
started with `findThreads(Predicate<Thread>)` on Windows and
`newDaemonThread(Runnable)` on Karina when sorted by proposal ID.

The fix canonicalizes input paths before assigning content-derived IDs. Native
parser wheel identity remains verified as a platform audit but is excluded from
the platform-independent production batch hash.

## Exact-I14 repaired result

Both eight-case permutation matrices passed with zero internal differences.
The cross-platform comparator checked nine complete production/evaluation
artifacts, the complete candidate-pack tree and the per-case platform-independent
component sets: 11/11 comparisons were byte-identical, difference count was
zero and the first divergent stage was `NONE`. Its report hash is
`0dda209bc0bbd172a01fcfe8047c38b552d34a655473df1fbff79e3237eb9ed9`.

# M-33.6e fresh metadata-only pool V4

`m336e_metadata_pool.py` freezes 78 new optional Maven/SCM metadata identities
covering 75 organizations, with no organization contributing more than two
candidates.  The seed registry contains coordinates, immutable SCM refs and
repository source prefixes only.  It contains no source-JAR bytes, archive
listing, Java text, parser output, callability facts or evaluator output.

Before any metadata request, `fresh_metadata_candidate_seeds` verifies the
current 30-entry append-only disclosure registry and rejects overlap with every
known prior family ID, Maven coordinate, source URL and SCM repository.  The
derived denylist also binds all disclosed archive and source-tree hashes for the
later post-acquisition overlap gate.

`scan_m336e_local_cache_names` inspects filenames and directory-layout metadata
only.  Exact source-JAR names, SCM archive names, repository checkouts and
extracted source-root names cause that candidate to be excluded.  The public
receipt fixes `source_body_bytes_read` at zero.  The exact Windows and Karina
cache roots are supplied at Q20/F20 time; cache contents are not embedded in
R20.

`probe_metadata_pool_v4` permits POM GET, source-JAR HEAD, checksum-sidecar GET,
signature HEAD and `git ls-remote`.  It rejects any source-JAR GET or nonzero
source-body byte receipt.  A successful pool has at least 48 candidate families,
at least 40 organizations, no more than two candidates per organization, zero
required candidates and only `OPTIONAL` candidates.  Metadata risk filtering
rejects obvious annotations/BOM/parent/plugin/processor/generator/native/test/
benchmark/shaded/starter/Kotlin/Scala roles without claiming final callability or
eligibility.

Failure analysis uses the actual candidate IDs.  It covers every individual
candidate, every organization, deterministic hash-partitioned 25% and 50%
subsets, checksum and SCM-only loss, multi-license review, largest-host loss,
GitHub metadata outage, Maven checksum outage, Apache correlation and the source
size tail.  Every scenario explicitly records
`claims_final_eligibility=false`; survivor counts are advisory potential capacity
only.

R20 does not execute the final metadata probe.  It freezes the implementation
and orchestration only.  The actual pool can be created only from a clean exact
Q20 worktree, after the complete disclosed Windows/Karina qualification passes.
No new final-candidate source-body bytes were received while implementing R20.

# M-33.6k exact-R27 qualification

R27 qualification is an offline replay of the preserved failed-F26 vault. It
does not issue a source network request, does not reuse the F26 run ID or ledger,
and writes all private material outside Git.

The qualification runner verifies the exact clean R27 commit and the immutable
Phase-0 receipts, runs 5,120 archive mutations plus the ten mixed-candidate
batches, creates 66 terminal receipts, seals a separate rehearsal vault, runs
qualification and selectability census, simulates an append-only 66-entry
disclosure registry update, and scans the public evidence tree for source,
absolute-path, and private-role leaks.

Compatibility files for the unchanged compiler-closure route are emitted as:

- `candidate_qualification.json`;
- `preflight_summary.json`;
- `source_entry_binding_manifest.json`;
- `selectability_census.json`;
- `selector_feasibility.json`.

The selector is deliberately not invoked by this runner. The subsequent
compiler-closure rehearsal owns the single rehearsal selector invocation.

Windows and Karina must run the same exact R27 tree. Platform-neutral receipts,
inventory, terminal matrix, archive decisions, census, selection, candidate
pack, and independent metrics must match byte-for-byte. Host-specific timing,
compiler executable identity, and command-log hashes are compared only under
their declared host roles.

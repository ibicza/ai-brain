# M-33.6e disclosure registry append protocol

Registry v2 extends the current manifest by an exact ordered suffix. Its append
receipt binds the previous manifest/count, sorted appended hashes/count, resulting
manifest/count, acquisition run, exact freeze SHA, and receipt hash.

Verification traverses every manifest parent, requires every v2 parent to be an
exact prefix, and rejects missing, skipped, or orphan manifests. The head must
have an identical content-addressed snapshot. Entry files are immutable and the
physical entry set must equal the head manifest exactly.

Append prevalidation rejects duplicate hashes and semantic identities before any
write. Writes are rolled back on failure. Tests use isolated registry copies and
cover 30→31, 30→54, and 30→78 chains plus deletion, replacement, reordering,
duplicate semantics, wrong parent, and skipped parent. The historical regression
binds the exact original six entry bytes/hashes without assuming current
cardinality is six.

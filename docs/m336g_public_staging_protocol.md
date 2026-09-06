# M-33.6g immutable public staging protocol

The staging gate operates on a newly materialized complete prospective tree. It freezes `(relative path, role, byte length, SHA-256, contract hash)` rows, validates the public pack and its exact installed copy independently, scans the whole tree against the sealed vault, binds candidate/installed/staging tree hashes, and snapshots the tree again after scanning.

Any new, omitted, unclassified, private-role, modified, uncontracted, source-bearing, or path-bearing byte fails the gate. The receipt binds the prospective Git tree identity. A release script must populate the index from the scanned tree, verify the prospective Git tree, then commit without regenerating artifacts.

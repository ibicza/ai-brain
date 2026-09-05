# M-33.6e untouched proof

Untouched status is established before F20 without opening a candidate source
body. Windows and Karina cache scans compare only candidate-derived filenames,
repository directory names, archive names, and shallow layout markers. A match
excludes the candidate; its contents are not inspected to restore eligibility.

The Q20 metadata probe is limited to POM bytes, source-JAR HEAD, checksum
sidecars, detached-signature availability, HTTP metadata, and immutable
`git ls-remote` results. The frozen pool, both cache receipts, and network
receipts must independently report zero source-body bytes. F20 binds their
hashes. The single source acquisition is forbidden until F20 is committed and
pushed.

Measured pool and cache results are intentionally deferred to Q20/F20. R20
contains only the fail-closed implementation and this protocol description.

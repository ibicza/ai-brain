# Installed Domain Registry

The SQLite registry is transactional and checksummed. It stores domain/version,
pack hash, approval, complete capability-resolution set, status, portable pack
path, install timestamp, and installation receipt. Approval and resolution
payload checksums and semantic hashes are verified, not merely indexed.

Supported operations are install, verify, list, show, deprecate, uninstall,
export, backup, and restore. Backup explicitly closes SQLite handles on Windows.
Uninstall removes activation metadata only; historical educational sessions are
not deleted and become `HISTORY_VALID_BUT_PACK_UNAVAILABLE` when appropriate.

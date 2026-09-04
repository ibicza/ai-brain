# M-33.6d local source vault contract

Raw source-JARs, POMs, SCM archives, extracted Java and legal documents belong only in a sealed local vault outside every Git worktree. Vault roots and files may not be symlinks or detectable reparse points. Every file must have an exact binding; extras and omissions fail.

Manifest rows bind candidate, canonical relative path, role, size, SHA-256, parent artifact and source-use receipt. The manifest binds F19, acquisition run, ordered rows, file count, tree hash, permission report, write-protection report and seal timestamp. Sealing and both copy verifiers require every file to be non-user-writable and reject links/reparse points, extras, omissions, row-hash drift, content drift and tree-hash drift. Only this hash manifest may enter public H19 evidence; raw bytes may not.

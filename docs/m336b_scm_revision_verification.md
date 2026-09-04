# M-33.6b SCM revision verification

`ScmRevisionProvider` canonicalizes a GitHub repository, resolves the frozen full tag ref using `git ls-remote`, records the tag object and peeled commit where applicable, and rejects an unresolved or caller-supplied commit.

Independently it retrieves a commit-addressed GitHub archive, verifies the final codeload URL is bound to that commit, inspects the tree, hashes every Java path and byte sequence, and captures LICENSE evidence at the same commit. Request and response hashes, the immutable 40-hex commit, archive hash, source-tree hash, license hash, and tag-to-commit result are sealed in a strict receipt.

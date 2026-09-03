# Authoritative identity versus aliases

Pack alias semantics schema 1 has three disjoint tables:

- `AuthoritativeIdentity`: unique pack record and canonical identity hash;
- `ExactReferenceAlias`: one exact reference to exactly one record;
- `SearchAliasEntry`: a casefolded lookup alias to a sorted tuple of records.

Only the first table decides uniqueness and trust. Exact references are used by
Knowledge IR relationships and ambiguous exact references fail preflight.
Search collisions compile normally; lookup returns `AMBIGUOUS_OVERLOAD` with
all sorted candidates. An exact receiver/member/JVM-parameter descriptor returns
one record. Existing packs without the self-bound `alias-semantics.<hash>`
artifact retain legacy pack-v2 interpretation; it is never silently applied to
new Java production packs.

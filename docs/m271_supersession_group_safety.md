# M-27.1 Supersession Group Safety

Supersession still requires the same subject, predicate, conflict-key
qualifiers, compatible value kind, valid temporal relation, active replacement
and no cycle.

Automatic conflict resolution has an additional membership rule: the
replacement must already belong to the exact ConflictGroup being resolved. A
valid same-domain supersession relation to an external claim may be stored, but
the group remains unresolved and the audit records
`SUPERSESSION_OUTSIDE_GROUP_NO_AUTO_RESOLUTION`. Resolving through an external
replacement requires explicit reviewed manual evidence.


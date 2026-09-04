# M-33.6 deep packability verification

The standalone verifier rebuilds the eligible denominator, binding cardinality,
identity and record IDs, runtime keys, duplicate/conflict/overload groups,
withholding reasons, candidate records, source bindings, exact references, search
aliases, unresolved references, ambiguous references, and final status.

It proves that eligible proposals are exactly the disjoint union of packable and
withheld proposals; exact references have one candidate target; search aliases only
name candidates; fatal identity groups withhold every implicated proposal; and each
trusted proposal is packable before candidate compilation.

The mandatory mutation battery removes a withholding reason, adds a non-packable
ID, omits a binding, changes a record ID, redirects an exact reference, inserts an
unknown search target, alters a group kind, hides a conflict, marks a failed report
PASS, and changes the candidate denominator. Accepted mutations must equal zero.

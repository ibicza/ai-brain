# M-33 limitations

M-33 is a bounded black-box proof, not open-web autonomy. The final selector
list and authority domains are closed, acquisition is offline after snapshot,
and runtime has no network access.

Natural-language extraction is intentionally conservative. The frozen patterns
cover exact definitions, bounded affine equations, and structurally explicit
API signatures. Narrative causality, interpretation, implicit taxonomy,
cross-sentence relations, complex mathematical notation, and API declarations
split across unsupported layouts may remain `REVIEW_REQUIRED`,
`UNSUPPORTED_KNOWLEDGE_KIND`, or `NEEDS_NEW_CAPABILITY`. Lower recall is an
acceptable Outcome B; guessing is not.

The typed solver is affine and exact-rational only. It rejects nonlinear forms,
dimension mismatch, incompatible units, absent applicability conditions, zero
division, and violated ranges. No Java compilation/execution capability is
included. Compile/run requests therefore return `NEEDS_NEW_CAPABILITY`.

No moral, moderation, NSFW, political, ideological, topic, personality, or
generic harmful-content policy is present. Abstention is based only on evidence,
authority, ambiguity, conflict, currentness, applicability, and capability.

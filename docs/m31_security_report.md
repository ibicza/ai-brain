# M-31 security report

The fail-closed battery covers altered hashes/schemas, duplicate IDs/JSON keys,
dangling and cyclic graphs, incompatible typed content, expression arity/depth,
unbounded powers, `eval`/import/exec/subprocess text, arbitrary procedure code,
unsafe IDs, symlinks, unexpected/oversized files, provider substitution, missing
capabilities, incomplete approval closures, MODEL approval, registry checksums,
cross-learner progress, stale authority, replayed confirmations, and crash stages.
Knowledge JSONL uses duplicate-key rejection, and pack closure now verifies that
every knowledge provenance, graph knowledge reference, adapter capability, source
hash, and exercise-family capability resolves inside the declared pack authority.

Generic CLI modules import no torch and perform no network access. Packs cannot
grant execution authority or relax Tool/Skill confirmation policy. No moral,
moderation, refusal, political, ideological, or topic policy was added.

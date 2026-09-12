# M-33.6k.5 Python launch inventory

The graph-first review classified every Python process that is reachable from the
M-33.6 final route. The detailed, path-free inventory is stored in
`artifacts/m336k5/python-launch-inventory.json`.

The historical F29 top-level process was ambient. Native stage workers, golden
authoring, exact quality, and Karina workers set `PYTHONNOUSERSITE=1` but started
without `-s`; local and remote workers also depended on `PYTHONPATH`. Replay,
evaluation, and runtime logic execute inside an already started native stage
process and inherit that process's startup state. Windows and Karina production
each start one additional Python worker; both workers now use the canonical K5
launcher and bind the same startup-receipt hash into the production summary. K5
exact quality also starts each Python-based check through an individual canonical
invocation plan; only the Java compiler check is a non-Python child.

M-33.6k.5 classifies every site and routes each external Python process through
the same startup policy: exact executable, `-s -B`, allowlisted environment,
stdlib-only verification, then imports from only the exact hashed repository
`src` and root (the latter is required by tracked test helpers under `scripts`).
In-process roles must carry the verified stage startup-receipt hash.

Unclassified Python process launch sites: **0**.

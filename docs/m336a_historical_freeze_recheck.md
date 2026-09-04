# Historical freeze recheck

The repaired verifier reads immutable Git objects for E14 -> F15 -> H15 -> E15. Blob loading is one `git cat-file --batch` operation rather than one process per file.

Result: exact parent chain true; commit messages true; merge count zero; historical M-33 SHA outside ancestry; H/E allowlists true; frozen-code mutations zero; branch/upstream equal; typed committed role manifest match true; historical false disclosure token count zero; protocol integrity `PASS`. The experiment outcome remains separately and explicitly `OUTCOME_C_BLOCKED` because acquisition stopped before selection and production.

The final Windows and Karina rechecks at I16 `6cf0cda35b19a3efb97f3e4bcfc78f1b3fdec970` produced byte-identical historical reports. Report hash: `1ab566ee4d06ecfbeff2095644702544a9d3c52a6de86cb6eeb3f82d7efcd18e`; evidence-file SHA-256: `65a38cc593dd69698b6f9116377d599b1eaaca79b5be4ac345ede42ced6a779d`.

# Historical freeze recheck

The repaired verifier reads immutable Git objects for E14 -> F15 -> H15 -> E15. Blob loading is one `git cat-file --batch` operation rather than one process per file.

Result: exact parent chain true; commit messages true; merge count zero; historical M-33 SHA outside ancestry; H/E allowlists true; frozen-code mutations zero; branch/upstream equal; typed committed role manifest match true; historical false disclosure token count zero; protocol integrity `PASS`. The experiment outcome remains separately and explicitly `OUTCOME_C_BLOCKED` because acquisition stopped before selection and production.

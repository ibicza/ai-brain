# M-34.4 final production trust metrics

Oracle-free production emitted 3,299 proposals: 3,162 trusted and 137 withheld across 65 observed production blocker categories. Internal production trust coverage is `0.958472`; this is not evaluator-measured correctness. Apache Commons IO contributed 1,336 proposals (1,265 trusted, 71 withheld), and Commons Lang contributed 1,963 proposals (1,897 trusted, 66 withheld).

Field-evidence counts are: required 127,617; present 127,617; exact 127,617; missing 0; extra 0; duplicate 0; wrong 0. Production field-evidence completeness and exactness are both `1.000000`. Duplicate-derived trusted proposals are 0. Java release consistency is `PASS` for exact Java 21, report hash `de5c40b7e6c463b3713d492dcda7c94c6189aa72d24d4d0cb197809aefac031e`.

The production file audit recorded 144,120 reads and 0 forbidden reads. The production process audit recorded 0 subprocesses, 0 socket attempts, 0 source/class executions, 0 annotation processors, and 0 `os.system` attempts.

Automatic trust precision, recall, correct/wrong trusted, correct/incorrect withheld, evaluator-backed evidence exactness, and resolution agreement are `N/A (NOT_MEASURED)`: candidate compilation failed before the independent oracle. A candidate pack was not completed, approved, installed, or replayed. This is a mandatory Outcome C rather than a safe-subset or PASS claim.

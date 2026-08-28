# M-29 Tutor Sessions

Tutor sessions are immutable snapshots over append-only presented, answer, grade, hint, solution, and abandoned events. Stored observations are submissions, grades, hints, status, and supported typed diagnoses; no intelligence, personality, age, disability, motivation, politics, or learning-style profile is inferred.

`EducationalSessionStore` uses a separate SQLite database with strict schema, checksummed artifacts, hash-chained events, atomic transactions, integrity checks, backup/restore, and moved-store verification. It never writes FactMemory.

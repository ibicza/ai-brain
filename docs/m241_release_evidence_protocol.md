# M-24.1 Release Evidence Protocol

Commit H contains release code, tests, scripts, documentation, manifest, and version 1.0.1. Local and Karina gates run against exact H. Only after both pass is annotated tag `stage1-v1.0.1` created on H.

Commit E is evidence-only: complete local/remote logs, final report, release evidence JSON, tag resolution, and summaries. The branch may end at E, but the release tag remains on H. The required `git diff H..E` path check proves that `src`, `tests`, `scripts`, `pyproject.toml`, and `artifacts/stage1` did not change.

This avoids claiming a commit hash from inside the commit that defines it. The evidence JSON records H and its tree after the tag and exact-SHA gates exist.

The broad `tmp/` ignore remains intentional. The current tree contains only reproducible project-generated smoke datasets, checkpoints, temporary RuleMemory files, and audit logs from earlier milestones; it contains no owned source, configuration, or release evidence. Narrowing it to one cache path would expose many equivalent generated experiment directories without improving release accountability.

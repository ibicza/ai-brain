# M-27 Unified Router CLI

Initialize and route a bounded local request:

```powershell
uv run ai-brain-router --root artifacts\stage2\m27\router init
uv run ai-brain-router --root artifacts\stage2\m27\router route-text --language en --text "Calculate 12.5 plus 3."
uv run ai-brain-router --root artifacts\stage2\m27\router verify
```

Optional `--fact-root` enables exact factual queries. Skill routing requires all four trusted paths: `--skill-registry`, `--rule-memory`, `--stage1-audit`, and `--stage2-audit`. Tool confirmation/execution use stored proposal hashes. Backup and restore use a checksummed SQLite snapshot. Importing the CLI does not load torch.

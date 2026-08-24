# Stage-1 v1 CLI

The production interface is under `ai-brain stage1`. Shared options are `--memory` and `--audit`.

```powershell
uv run ai-brain stage1 language-help --lang ru
uv run ai-brain stage1 propose-language --lang en --text "Move every item from A into B; leave C and D unchanged; stop when A is empty." --output proposal.json
uv run ai-brain stage1 review --proposal proposal.json --output reviewed.json
uv run ai-brain stage1 verify --proposal reviewed.json --proposal-output verified.json --candidate-output candidate.json
uv run ai-brain stage1 approve --proposal verified.json --candidate candidate.json --identity operator --proposal-output approved.json --approval-output approval.json
uv run ai-brain stage1 install --proposal approved.json --candidate candidate.json --approval approval.json --proposal-output installed.json
uv run ai-brain stage1 list
uv run ai-brain stage1 inspect --rule-id rule-00001-...
uv run ai-brain stage1 execute --proposal installed.json --rule-id rule-00001-... --state '{"R0":2,"R1":3,"R2":4,"R3":5}' --proposal-output executed.json
uv run ai-brain stage1 audit-replay
```

`propose-form` accepts a strict specification JSON object. `propose-dsl` accepts a canonical DSL file plus a strict specification file. Workflow artifacts are UTF-8 JSON and should be passed unchanged between commands.

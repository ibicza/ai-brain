# Stage-1 v1 CLI

`ai-brain-stage1` is the trusted production executable. `ai-brain stage1` remains a development convenience and loads the broader project stack.

```powershell
uv run ai-brain-stage1 language-help --lang ru
uv run ai-brain-stage1 propose-language --lang en --text "Move every item from A into B; leave C and D unchanged; stop when A is empty." --output proposal.json
uv run ai-brain-stage1 review --proposal proposal.json --output reviewed.json
uv run ai-brain-stage1 verify --proposal reviewed.json --proposal-output verified.json --candidate-output candidate.json
uv run ai-brain-stage1 review-verification --proposal verified.json --candidate candidate.json --proposal-output verified-reviewed.json --review-output verified-review.json
uv run ai-brain-stage1 approve --proposal verified-reviewed.json --candidate candidate.json --review verified-review.json --identity operator --proposal-output approved.json --approval-output approval.json
uv run ai-brain-stage1 install --proposal approved.json --candidate candidate.json --review verified-review.json --approval approval.json --proposal-output installed.json --receipt-output receipt.json
uv run ai-brain-stage1 execute --proposal installed.json --receipt receipt.json --rule-id rule-00001-... --state '{"R0":2,"R1":3,"R2":4,"R3":5}' --proposal-output executed.json --result-output result.json
uv run ai-brain-stage1 audit-replay
```

Shared `--memory` and `--audit` options precede the subcommand. Execution defaults to no trace. `--trace` enables bounded capture; limit flags cannot exceed compiled hard ceilings. `migrate-rule-memory --source old.json --destination new.json` is the only checksum-less migration path.

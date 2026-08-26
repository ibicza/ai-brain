# M-26 Fact CLI

The `ai-brain-facts` entry point imports no torch.

```powershell
uv run ai-brain-facts --root artifacts/facts/demo init
uv run ai-brain-facts --root artifacts/facts/demo add-entity --json entity.json
uv run ai-brain-facts --root artifacts/facts/demo add-predicate --json predicate.json
uv run ai-brain-facts --root artifacts/facts/demo add-source --file source.json --metadata source-metadata.json
uv run ai-brain-facts --root artifacts/facts/demo propose-claim --json proposal.json
uv run ai-brain-facts --root artifacts/facts/demo attach-evidence --json evidence.json --proposal-id proposal.demo
uv run ai-brain-facts --root artifacts/facts/demo review-claim --proposal-id proposal.demo --reviewer user
uv run ai-brain-facts --root artifacts/facts/demo approve-claim --proposal-id proposal.demo --reviewer user
uv run ai-brain-facts --root artifacts/facts/demo commit-claim --proposal-id proposal.demo --approval-id fact_approval_...
uv run ai-brain-facts --root artifacts/facts/demo query --json query.json
uv run ai-brain-facts --root artifacts/facts/demo verify
```

Additional commands cover history, conflicts, supersession, claim/source retraction, backup, restore, export, and audit replay. Immutable workflow inputs use JSON files; credentials and network fetching are not supported.

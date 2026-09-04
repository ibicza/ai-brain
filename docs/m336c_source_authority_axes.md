# M-33.6c source authority axes

`SourceAuthorityDecision` keeps four questions independent:

1. `SourceAuthenticityStatus` proves where exact bytes came from.
2. `KnowledgeAcquisitionEligibility` controls parsing, extraction and local evaluation.
3. `SourceUseAuthorizationReceipt` records externally supplied retention/use scopes.
4. `PublicationEligibilityDecision` is emitted separately for raw source, excerpts, derived packs and metrics.

Authorization receipts are typed and hash-bound. `MODEL`, `ASSISTANT` and `GENERATED_MODEL` authority kinds are rejected, and an in-memory scope change invalidates the receipt hash. Local analysis never implies raw publication. These are provenance/storage controls only; no moral, moderation, refusal, political, ideological or topic policy was added.

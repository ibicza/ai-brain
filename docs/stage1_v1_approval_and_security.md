# Stage-1 v1 Approval And Security

Installation requires the workflow `VERIFIED -> VERIFIED_REVIEWED -> APPROVED`. Direct approval from `VERIFIED` is rejected.

The verified review displays the original input, final specification, semantic effect, changed and preserved registers, termination, ordered phases, compiler mode, canonical candidate, static/abstract/property results, full evidence, hashes, version, and limitations. Its deterministic hash binds its complete content.

`ApprovalEnvelope` binds proposal, specification, candidate, evidence, verified-review, approver identity/type/timestamp, and Stage-1 version. A v1.0.0 approval cannot authorize a v1.0.1 installation. Installation revalidates every binding and reruns property verification.

Installation emits an immutable receipt binding the proposal to one rule ID and semantic hash. Service execution requires that receipt and rejects another rule. State, step, and trace limits fail with typed errors; failures are audited without raw state.

Audit events carry the content hashes needed to reconstruct the workflow. The hash chain is tamper-evident for existing records, but deletion of the tail requires an external checkpoint or anchor to detect.

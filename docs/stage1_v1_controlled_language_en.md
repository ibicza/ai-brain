# Stage-1 v1 Controlled Language: EN

A command must explicitly name the operation, every source, transfer destination, preserved registers, termination condition, and the phase order for `DROP_THEN_TRANSFER`.

Example:

```text
Move every item from A and B into C; leave D unchanged; stop when A and B are empty.
```

The frozen vocabulary includes `move`, `transfer`, `convey`, `channel`; `clear`, `remove`, `purge`, `expunge`; and the preserve/stop phrases shown by `ai-brain stage1 language-help --lang en`.

A missing field returns `CLARIFICATION_REQUIRED`, a contradiction returns `CONTRADICTORY`, and an unknown operation returns `UNSUPPORTED`. The parser does not guess. One typed clarification round is available.

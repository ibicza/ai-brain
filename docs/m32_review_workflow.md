# Review workflow

Review decisions are immutable and hash-bound: `APPROVE`, `REJECT`, `EDIT_AND_APPROVE`, `REVIEW_REQUIRED`, or `NEEDS_NEW_CAPABILITY`. Every approved proposal receives a separate approval that binds original proposal, approved proposal, and review hashes.

A blank identity or `MODEL` identity cannot approve. Edited content is accepted only with `EDIT_AND_APPROVE` and its hash remains in the review. Approval still does not install a pack.

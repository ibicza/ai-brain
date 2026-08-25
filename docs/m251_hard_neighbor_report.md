# M-25.1 Hard Neighbor Report

## Construction

Every hard row names an installed target and installed counterfactual neighbor. Their normalized catalog records differ in exactly one conceptual field: ordered sources or destination. A matched counterfactual surface is rendered with the same language, lexicon, template, wrapper, suffix, and punctuation seed. Pair IDs and changed-field labels remain hidden.

## Results

| Recipe | Split | top1 | pairwise | switch | mean margin |
|---|---|---:|---:|---:|---:|
| sanitized baseline | development | 0.8899 | 0.9193 | 0.7486 | 0.5423 |
| sanitized + hard loss | development | 0.8844 | 0.9119 | 0.7376 | not selected |
| targeted sanitized | development | 0.8917 | 0.9321 | 0.7523 | positive |
| targeted sanitized | blind | 0.7140 | 0.8160 | 0.7140 | positive |

Explicit hard-negative loss did not improve the unchanged model and was not selected alone. The one allowed representation fix adds operation/register-role features and improves development pairwise discrimination, but blind counterfactual switching remains below the `0.90` goal.

Character n-gram retrieval has blind pairwise `0.8680` but overall top1 only `0.3460`; pairwise alone is not sufficient evidence of correct routing. Learned results remain assistive and non-exact.

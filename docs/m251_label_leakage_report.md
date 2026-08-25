# M-25.1 Label Leakage Report

## Development Diagnostics

| Diagnostic | Result | Gate |
|---|---:|---:|
| wrapper-only AUROC | 0.5016 | <= 0.60 |
| length/punctuation AUROC | 0.5720 | <= 0.60 |
| complete alias/example substring | 0.0000 | 0.0000 |
| prompt intersection | 0 | 0 |

Both classifier alerts are executable acceptance gates. The initial V2 draft failed them because negative requests were shorter and always contained a wrapper; generation was corrected before any learned model or blind result was selected.

Character four-gram Jaccard overlap is reported per slice and corpus. Development mean overlap is approximately `0.0588` for rich, `0.0151` for sanitized, and `0.0026` for minimal. Complete corpus-line subsequence overlap is zero for all three.

Blind leakage values are computed only as part of the single frozen blind opening.

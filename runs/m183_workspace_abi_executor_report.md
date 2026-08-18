# M-18.3 Canonical Workspace ABI Executor Report

## Checks

- ruff format/check/pytest: passed
- commit hash at report build: `a1a70d7`
- device: `cuda:0 (NVIDIA GeForce RTX 3050 Laptop GPU)`

## Canonical Workspace ABI

Canonical state is source-invariant:

```text
<WS>
<OP_ADD>
<A> 27
<B> 35
</WS>
```

## Dataset Verification

| item | value |
|---|---:|
| executor_train_count | 6400 |
| bridge_train_count | 1600 |
| binding_bridge_train_count | 600 |
| oracle_bridge_train_count | 8000 |
| prompt_intersections | {'executor_train_vs_eval\\binding_to_workspace.jsonl': 0, 'executor_train_vs_eval\\bridge\\heldout_operands.jsonl': 0, 'executor_train_vs_eval\\bridge\\mixed.jsonl': 0, 'executor_train_vs_eval\\bridge\\seen.jsonl': 0, 'executor_train_vs_eval\\bridge\\unseen.jsonl': 0, 'executor_train_vs_eval\\executor\\standalone_heldout_operands.jsonl': 0, 'executor_train_vs_eval\\executor\\standalone_seen.jsonl': 0, 'executor_train_vs_eval\\executor\\standalone_unseen.jsonl': 0, 'executor_train_vs_eval\\executor\\workspace_heldout_operands.jsonl': 0, 'executor_train_vs_eval\\executor\\workspace_seen.jsonl': 0, 'executor_train_vs_eval\\executor\\workspace_unseen.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_0.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_1.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_16.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_2.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_32.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_4.jsonl': 0, 'executor_train_vs_eval\\oracle_bridge\\junk_8.jsonl': 0} |

## Canonical Symbolic vs Workspace Arithmetic Equivalence

| split | standalone | workspace | gap |
|---|---:|---:|---:|
| seen | 0.9900 | 0.9850 | 0.0050 |
| unseen | 0.9900 | 0.9900 | 0.0000 |
| heldout_operands | 0.1450 | 0.2600 | 0.1150 |

## Teacher-Forced Workspace Upper Bound

| split | overall | ADD | SUB |
|---|---:|---:|---:|
| seen | 0.9850 | 1.0000 | 0.9434 |
| unseen | 0.9900 | 1.0000 | 0.9667 |
| heldout_operands | 0.2600 | 0.0900 | 0.3867 |

## Retrieval -> Workspace Parse

skipped

## Executor Given Workspace

blocked: teacher-forced workspace executor did not pass heldout .98 gate

## End-To-End Relevant Arithmetic

skipped: upstream gate did not pass

## Heldout Operands

| component | heldout score |
|---|---:|
| workspace executor | 0.2600 |
| retrieval->workspace | 0.0000 |
| end-to-end final | 0.0000 |

## Binding Depth -> Workspace -> Final

skipped: executor gate did not pass

## Oracle Chunk -> Workspace -> Final

skipped: executor gate did not pass

## Shared vs Frozen Executor Retention

| design | arithmetic before | arithmetic after bridge | drop |
|---|---:|---:|---:|
| frozen executor | 0.2600 | 0.2600 | 0.0000 |
| shared core | not run | not run | not run |

## ADD_SUB

skipped: workspace bridge/executor gates did not pass

## Held-Out SUB_ADD

skipped: ADD_SUB gate did not pass

## Decision

OUTCOME C precursor: canonical ABI is defined, but the neural arithmetic executor did not reach the .98 heldout workspace upper-bound gate. Stop before bridge/composition; first make workspace-form arithmetic match standalone arithmetic or replace text serialization with a stronger slot interface.
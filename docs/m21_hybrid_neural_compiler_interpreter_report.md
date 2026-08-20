# M-21 Hybrid Neural Compiler + Exact Interpreter

## Remote Environment

- hostname: `karina`
- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB`
- branch: `exp/neural-symbolic-interpreter`

## M-20.1a Starting Point

M-20.1a found replay50 `program_seen=1.0`, `heldout_binding=1.0`, but `heldout_program=0.1250` and `MERGE_TWO=0.0911`; policy head improved MERGE_TWO to `0.4193` but did not solve heldout AST composition.

## Literature Architecture Map

See `docs/m21_architecture_research_notes.md`. The implemented boundary follows NPI/NSM/Forth-style decomposition: learned structured selection, exact typed execution.

## Typed AST

Implemented `ProgramAst`, `ClauseAst`, `PredicateAst`, `ActionAst`, `BindingAst`, and `RegisterState` with alpha-normalized and order-insensitive semantic hashes plus deterministic validation.

## Exact Interpreter Upper Bound

| split | clause acc | action acc |
|---|---:|---:|
| alpha_renamed | 1.0000 | 1.0000 |
| clause_order | 1.0000 | 1.0000 |
| distractor_16 | 1.0000 | 1.0000 |
| distractor_8 | 1.0000 | 1.0000 |
| heldout_binding | 1.0000 | 1.0000 |
| heldout_merge_two | 1.0000 | 1.0000 |
| heldout_predicate_composition | 1.0000 | 1.0000 |
| heldout_program | 1.0000 | 1.0000 |
| merge_three | 1.0000 | 1.0000 |
| merge_two_11_20 | 1.0000 | 1.0000 |
| merge_two_21_50 | 1.0000 | 1.0000 |
| merge_two_51_100 | 1.0000 | 1.0000 |
| seen_ast | 1.0000 | 1.0000 |

## Deterministic DSL Parser

| split | clause acc | action acc |
|---|---:|---:|
| alpha_renamed | 1.0000 | 1.0000 |
| clause_order | 1.0000 | 1.0000 |
| distractor_16 | 1.0000 | 1.0000 |
| distractor_8 | 1.0000 | 1.0000 |
| heldout_binding | 1.0000 | 1.0000 |
| heldout_merge_two | 1.0000 | 1.0000 |
| heldout_predicate_composition | 1.0000 | 1.0000 |
| heldout_program | 1.0000 | 1.0000 |
| merge_three | 1.0000 | 1.0000 |
| merge_two_11_20 | 1.0000 | 1.0000 |
| merge_two_21_50 | 1.0000 | 1.0000 |
| merge_two_51_100 | 1.0000 | 1.0000 |
| seen_ast | 1.0000 | 1.0000 |

## Oracle Component Ladder

Oracle parser/interpreter is 1.0. The structured selector condition removes text parsing and action serialization; exact action resolution maps selected clauses to physical actions.

## Structured Binding

Bindings are represented as pointer IDs and logical-variable to physical-register matrices. Text binding is not used inside the selector.

## Hierarchical Clause Selector

| split | clause acc | resolved action acc |
|---|---:|---:|
| alpha_renamed | 1.0000 | 1.0000 |
| clause_order | 1.0000 | 1.0000 |
| distractor_16 | 1.0000 | 1.0000 |
| distractor_8 | 1.0000 | 1.0000 |
| heldout_binding | 1.0000 | 1.0000 |
| heldout_merge_two | 1.0000 | 1.0000 |
| heldout_predicate_composition | 1.0000 | 1.0000 |
| heldout_program | 0.9611 | 0.9611 |
| merge_three | 0.8833 | 0.8833 |
| merge_two_11_20 | 1.0000 | 1.0000 |
| merge_two_21_50 | 1.0000 | 1.0000 |
| merge_two_51_100 | 1.0000 | 1.0000 |
| seen_ast | 1.0000 | 1.0000 |

## Exact vs Neural Action Resolution

Exact action resolution is used after selector choice. M-20.1a policy-head numbers are reported in the bakeoff as the finite neural action resolver control; LM action generation remains the weakest interface.

## Structured AST Generalization

| split | closed-loop final | invalid |
|---|---:|---:|
| heldout_binding | 1.0000 | 0.0000 |
| heldout_merge_two | 1.0000 | 0.0000 |
| heldout_program | 0.7083 | 0.2917 |
| merge_three | 0.1250 | 0.8750 |
| merge_two_11_20 | 1.0000 | 0.0000 |
| merge_two_21_50 | 1.0000 | 0.0000 |
| merge_two_51_100 | 1.0000 | 0.0000 |
| seen_ast | 1.0000 | 0.0000 |

## MERGE_TWO Phase Results

| phase | count | clause acc |
|---|---:|---:|
| A_TO_B_SWITCH | 320 | 1.0000 |
| FINAL_HALT | 384 | 1.0000 |
| PHASE_A_MOVE | 1344 | 1.0000 |
| PHASE_B_MOVE | 640 | 1.0000 |

## Neural Compiler

| split | semantic exact | deterministic parser exact |
|---|---:|---:|
| heldout_template | 0.0000 | 1.0000 |
| seen_template | 0.9000 | 1.0000 |

## AST Validity and Semantic Accuracy

- compiler validity: `1.0000`
- compiler semantic exact: `0.6000`
- deterministic parser semantic exact: `1.0000`

## Verifier / Repair

Verifier rejects unknown variables, invalid register references, invalid action arity, non-exhaustive programs, and overlapping clauses. Repair was not run.

## Compiler + Exact Interpreter

End-to-end compiler execution is bounded by semantic AST accuracy; exact interpreter succeeds when AST is correct.

## Heldout Program Instances

- one-step clause: `0.9611`; resolved action: `0.9611`; closed-loop: `0.7083`

## Heldout MERGE_TWO

- one-step clause: `1.0000`; resolved action: `1.0000`; closed-loop: `1.0000`

## Heldout MERGE_THREE

- one-step clause: `0.8833`; resolved action: `0.8833`; closed-loop: `0.1250`

## Counterfactual Controls

```json
{
  "alpha_equivalent": {
    "R0": 0,
    "R1": 0,
    "R2": 5,
    "R3": 0
  },
  "correct": {
    "R0": 0,
    "R1": 0,
    "R2": 5,
    "R3": 0
  },
  "reordered_equivalent": {
    "R0": 0,
    "R1": 0,
    "R2": 5,
    "R3": 0
  },
  "swapped_binding": {
    "R0": 2,
    "R1": 0,
    "R2": 3,
    "R3": 0
  },
  "wrong_program": {
    "R0": 0,
    "R1": 3,
    "R2": 0,
    "R3": 0
  }
}
```

## Optional Program Induction

Not gated. Demonstration-to-program induction requires compiler/interpreter success first.

## Architecture Bakeoff

| architecture | heldout program | MERGE_TWO |
|---|---:|---:|
| flat text LM policy | 0.1250 | 0.0911 |
| flat policy head | 0.2240 | 0.4193 |
| exact AST + hierarchical selector + exact resolver | 0.7083 | 1.0000 |
| neural compiler + exact interpreter | 0.0000 | 0.0000 |
| deterministic parser + exact interpreter upper bound | 1.0000 | 1.0000 |

## Multi-Seed

One exploratory seed only. Multi-seed gate was not reached unless a candidate exceeds 0.90.

## Interpretation

OUTCOME C: exact AST plus hierarchical selector still fails; use fully exact interpreter at runtime.

## Recommended Stage-1 Architecture

Use the fully exact interpreter at runtime and train neural models to generate/select complete verified ASTs, not execute clauses.

## Checks

- local/remote ruff + pytest + CUDA smoke: passed
- commit hash at run: `0a231f4`

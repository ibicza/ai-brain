# M-21 Architecture Research Notes

## Neural Programmer-Interpreter

Primary source: https://arxiv.org/abs/1511.06279

- Neural part: recurrent core chooses subprogram calls and arguments from program embeddings plus environment encodings.
- Exact part: environment state and low-level effects are external to the recurrent hidden state.
- Variables/bindings: represented as program arguments and environment pointers, not plain text.
- Composition: higher-level programs call lower-level programs with shared recurrent machinery.
- OOD measurement: addition, sorting, and 3D canonicalization with heldout sizes/tasks.
- Minimal ai-brain idea: do not ask one flat text policy to rediscover execution; separate clause/program selection from exact external-state updates.

## Neural Symbolic Machines

Primary source: https://arxiv.org/abs/1611.00020

- Neural part: seq2seq programmer maps utterances to executable programs.
- Exact part: Lisp interpreter executes programs and prunes invalid candidates.
- Variables/bindings: key-variable memory supports compositional program construction.
- Composition: symbolic programs are generated and executed by a non-differentiable computer.
- OOD measurement: semantic parsing generalization on Freebase/WebQuestionsSP under weak supervision.
- Minimal ai-brain idea: a neural compiler should produce a typed AST, while deterministic verification/execution should be exact.

## Differentiable Forth Interpreter

Primary source: https://arxiv.org/abs/1605.06640

- Neural part: fills trainable behavior slots inside program sketches.
- Exact part: Forth-like abstract machine provides procedural structure, stack/memory discipline, and control flow.
- Variables/bindings: typed machine state and stack positions carry values.
- Composition: written sketches compose learned local operations under a known interpreter.
- OOD measurement: addition, sorting, and story quantity reasoning with program-structure priors.
- Minimal ai-brain idea: preserve exact interpreter structure and only learn uncertain local decisions.

## Differentiable Tree Machine

Primary source: https://arxiv.org/abs/2306.00751

- Neural part: agent selects tree operations.
- Exact part: external tree memory and operation semantics maintain symbolic structure.
- Variables/bindings: represented through tree nodes and operation arguments rather than flattened strings.
- Composition: repeated exact tree operations build transformations.
- OOD measurement: synthetic semantic parsing/language generation compositional splits.
- Minimal ai-brain idea: use structured AST tensors and shared clause encoders rather than raw BPE streams.

## ExeDec

Primary source: https://arxiv.org/abs/2307.13883

- Neural part: predicts execution subgoals/subproblem decomposition.
- Exact part: synthesis/execution checks constrain search and validate progress.
- Variables/bindings: intermediate execution states serve as structured subgoals.
- Composition: decomposes complex programs into executable subgoals.
- OOD measurement: compositional RobustFill and DeepCoder program-synthesis benchmarks.
- Minimal ai-brain idea: measure MERGE_TWO by execution phase and decompose selector/action/binding failures.

## Execution-Guided / Grammar-Constrained Program Prediction

Primary sources: https://openreview.net/forum?id=H1gfOiAqYm and https://aclanthology.org/2021.findings-acl.108.pdf

- Neural part: proposes program tokens or structured meaning representations.
- Exact part: type systems, grammars, parsers, and execution reject invalid continuations.
- Variables/bindings: grammar and type constraints keep slots well-formed.
- Composition: generation is constrained by formal syntax and checked by execution.
- OOD measurement: executable query/program accuracy and invalid-program rate.
- Minimal ai-brain idea: canonical DSL should use a deterministic parser; neural compilation is only needed for noisy/flexible surfaces.

## Role-Filler Binding

Primary sources: https://arxiv.org/abs/1902.09006 and https://arxiv.org/abs/2012.07172

- Neural part: learns to retrieve fillers for abstract roles, often helped by external memory.
- Exact part: task schema defines roles/fillers and evaluation checks arbitrary role reassignment.
- Variables/bindings: role identity and filler identity must remain disentangled.
- Composition: schemas are reused with novel fillers.
- OOD measurement: heldout or correlation-violating role/filler pairings.
- Minimal ai-brain idea: represent logical variables and physical registers as a binding matrix or pointer vector, not as free-form binding text.

## M-21 Design Choice

The most conservative next boundary for ai-brain is:

1. deterministic canonical DSL parser for formal program text;
2. typed AST verifier;
3. exact interpreter for predicate/action/binding/environment semantics;
4. neural clause selector only where execution requires a learned choice;
5. neural compiler only as a separate front-end experiment for non-canonical surfaces.


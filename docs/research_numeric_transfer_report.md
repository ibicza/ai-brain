# Numeric Range Transfer Research Report

## Goal

Find and test practical fixes for the ai-brain shifted-range failure observed in M-11.1/M-11.2, without jumping straight to long 30k/50k training or a large new architecture.

## Checks

- `uv run ruff format src tests`: passed (`51 files left unchanged`)
- `uv run ruff check src tests`: passed
- `uv run pytest -q`: passed (`139 passed`)
- `.\scripts\update-code-graph.ps1`: attempted; blocked by PyPI timeout fetching `code-review-graph`
- Source HEAD before this report commit: `92d96474ab52908ee665d95d0c7d6dde3b3531af`
- Device used for experiments: NVIDIA GeForce RTX 3050 Laptop GPU (`cuda:0`, 4GB)

## Literature Scan

I reviewed several dozen papers, pages, and adjacent mechanistic/algorithmic-reasoning notes. The recurring fixes cluster into these hypotheses:

- Representation: digit-level tokenization, right-to-left/lower-endian digits, digit-place embeddings, role embeddings, and compact numeric spans.
- Position: relative/structured positional descriptions, index hints, and avoiding brittle absolute-position shortcuts.
- Data: train-set priming, curriculum diversity, and including a small number of long/shifted examples.
- Scratchpads: concise intermediate steps help; verbose traces can hurt by increasing sequence length and generation burden.
- Architecture: recurrent/active-memory processors, compiled rule modules, continuous/single-token number embeddings, or explicit digit/place/role embeddings.

Most actionable for the current codebase was train-set priming: it is cheap, diagnostic, and directly supported by arithmetic length-generalization literature.

## Sources Reviewed

- [Length Generalization in Arithmetic Transformers](https://huggingface.co/papers/2306.15400): Relative position embeddings and train-set priming; directly motivated shifted-prime experiments.
- [Tokenization counts: impact of tokenization on arithmetic](https://axi.lims.ac.uk/paper/2402.14903): Number tokenization and right-to-left representations; motivated r2l_numeric.
- [Transformers Can Do Arithmetic with the Right Embeddings](https://huggingface.co/papers/2405.17399): Digit-position embeddings and task structure; supports future embedding work.
- [Positional Description Matters for Transformers Arithmetic](https://huggingface.co/papers/2311.14737): Representations and positional descriptions matter for larger-number arithmetic.
- [Teaching Arithmetic to Small Transformers](https://proceedings.iclr.cc/paper_files/paper/2024/hash/6bf82fdcbd92b6a7793b3894422d2437-Abstract-Conference.html): Formatting, instructive data, and intermediate results improve small transformers.
- [Exploring Length Generalization in Large Language Models](https://research.google/pubs/exploring-length-generalization-in-large-language-models/): Naive finetuning fails; scratchpads help length generalization.
- [What Algorithms can Transformers Learn?](https://www.alphaxiv.org/abs/2310.16028): Task simplicity, data diversity, and index hints explain length generalization.
- [A Formal Framework for Understanding Length Generalization in Transformers](https://machinelearning.apple.com/research/length-generalization-transformers): Formal account of when length generalization is identifiable.
- [Length Extrapolation of Transformers: survey](https://axi.lims.ac.uk/paper/2312.17044): Position encoding survey; informs architecture-side next steps.
- [Neural GPUs Learn Algorithms](https://www.sciencestack.ai/paper/1511.08228v3): Lower-endian arithmetic, recurrence, curriculum, and algorithmic generalization.
- [Improving the Neural GPU Architecture for Algorithm Learning](https://huggingface.co/papers/1702.08727): Decimal multiplication and active-memory architecture improvements.
- [Neural Programmer-Interpreters](https://mlanthology.org/iclr/2016/reed2016iclr-neural/): Execution traces and compositional subprograms for addition/sorting.
- [Neural algorithmic reasoning](https://pmc.ncbi.nlm.nih.gov/articles/PMC8276006/): Algorithmic processors as a broader framework.
- [xVal continuous number encoding](https://polymathic-ai.org/blog/xval/): Continuous number encodings; future architectural path, not used in this text-only loop.
- [Efficient numeracy through single-token number embeddings / BitTokens overview](https://www.alphaxiv.org/overview/2510.06824v1): Single-token numerical representation tradeoffs.
- [Understanding Addition and Subtraction in Transformers](https://huggingface.co/papers/2402.02619): Small specialized transformers can learn arithmetic circuits.
- [Language Models are Symbolic Learners in Arithmetic](https://openreview.net/forum?id=QSblPg1xUM): Shortcut/subgroup learning explains why arithmetic remains brittle.
- [Understanding In-context Learning of Addition via Activation Subspaces](https://openreview.net/forum?id=4ejlQOH2AY): Few-shot arithmetic signals and activation subspaces.
- [Grokking modular arithmetic](https://dblp.org/rec/journals/corr/abs-2301-02679): Mechanistic/grokking angle for arithmetic learning.
- [Can Neural Networks Learn Symbolic Rewriting?](https://cl-informatik.uibk.ac.at/research/publications/publications-2019/can-neural-networks-learn-symbolic-rewriting): Symbolic rewriting as adjacent algorithmic generalization.
- [Circuit explained: compositional generalization](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0340088): Position/identity disentanglement for compositional rules.
- [Compositional Processing Emerges in Neural Networks Solving Math Problems](https://pmc.ncbi.nlm.nih.gov/articles/PMC8491571/): Intermediate-value representations in math transformers.
- [Mastering Symbolic Operations with Compiled Neural Networks](https://openreview.net/forum?id=tpIUgkq0xa): Compiled rule modules as an architecture-side path.

Additional adjacent threads considered: ALiBi/RoPE/NoPE/FIRE length extrapolation families, neural stacks/queues/Turing-machine variants, modular-arithmetic grokking analyses, and specialized arithmetic tokenizers. I did not implement these deeper architecture changes in this loop because the request was to iterate from cheap tests first.

## Experiments

All datasets enforce unique prompts and zero train/eval intersections. All runs used `tiny`, `batch-size=8`, `sequence-length=256`, and answer-only loss unless noted.

| experiment | preset | format | train mix | same final NEM | shifted final NEM | verdict |
| --- | --- | --- | --- | ---: | ---: | --- |
| M-11.2 reference | quantity_direct | place_role_numeric | 100% same | n/a | 0.3970 | below useful |
| r2l pilot | arithmetic | r2l_numeric | 100% same | 0.0990 | 0.0100 | below useful |
| 10% shifted-prime | quantity_direct | place_role_numeric | 90% same / 10% shifted | 1.0000 | 0.9940 | strong |
| 10% shifted-prime | arithmetic | scratchpad | 90% same / 10% shifted | 0.1595 | 0.0245 | below useful |
| 10% shifted-prime | state_change | place_role_numeric | 90% same / 10% shifted | 0.6240 | 0.5720 | strong |
| 10% shifted-prime | sorting_short | normal_answer | 90% same / 10% shifted | 0.6070 | 0.0290 | below useful |
| 20% shifted-prime | arithmetic | scratchpad | 80% same / 20% shifted | 0.1305 | 0.0255 | below useful |
| 20% shifted-prime | sorting_short | normal_answer | 80% same / 20% shifted | 0.4390 | 0.0380 | useful |
| 50% shifted-prime | arithmetic | scratchpad | 50% same / 50% shifted | 0.1080 | 0.0355 | useful |

## Best Results

| preset | old best shifted | best new shifted | delta | best recipe | threshold verdict |
| --- | ---: | ---: | ---: | --- | --- |
| quantity_direct | 0.3720 | 0.9940 | +0.6220 | 10% shifted-prime + place_role_numeric | strong |
| arithmetic | 0.0135 | 0.0355 | +0.0220 | 50% shifted-prime + scratchpad | useful |
| state_change | 0.2327 | 0.5720 | +0.3393 | 10% shifted-prime + place_role_numeric | strong |
| sorting_short | 0.0090 | 0.0380 | +0.0290 | 20% shifted-prime + normal_answer | useful |

## By-Task Highlights

- `quantity_direct`: 10% priming made shifted almost solved: direct/location/known_zero all near 0.99-1.00 final NEM.
- `state_change`: 10% priming made no-change and insufficient-start robust, but `state_change.add/subtract` remain near zero under shifted range.
- `sorting_short`: 20% priming crosses useful overall, but ascending is much easier than descending in shifted eval.
- `arithmetic`: 50% priming crosses useful overall, but the gain comes mostly from add/subtract; `double_step` remains 0.0 shifted final NEM.

## Interpretation

The dominant failure was not solved by verbose textual role tags alone. The strongest intervention was train-set priming with shifted-range examples, matching the train-set priming result from arithmetic length-generalization literature. This strongly suggests the tiny model needed explicit coverage of shifted numeric symbols/ranges to avoid brittle shortcut rules.

However, arithmetic is different from copy/state/sort: even with 50% shifted exposure, full arithmetic remains weak. That points to a second bottleneck: algorithmic rule/capacity, especially multi-step carry/borrow composition and double-step tasks.

## Recommendation

Next implementation step should turn range priming into a first-class dataset feature, then test it with a more principled compact representation. Suggested order:

1. Add official `generate-range-primed` support with `--shifted-prime-fraction`, manifest checks, and stable seeds.
2. Use 10% shifted-prime for quantity/state, 20% for sorting, and 50% for arithmetic scratchpad as the new tiny diagnostic baseline.
3. For arithmetic, split reporting by subtask and separately attack `double_step` with stronger primitive curriculum or explicit carry/borrow subtask pretraining.
4. Then implement model-side digit/place/role embeddings or a compact digit-level tokenizer; do not return to verbose text tags as the main path.





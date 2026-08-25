# M-25 Stage-2 Skill Registry Architecture

## Trust Boundary

```text
ProgramSpecification ---------------------> exact specification/signature match
controlled RU/EN -> frozen parser --------> exact specification/signature match
free text -> lexical/ngram/BM25/bi-encoder -> ranked candidates only
                                                    |
                                                    v
                                      explicit selection confirmation
                                                    |
                                                    v
SkillRegistry + RuleMemory + installed receipt -> Stage1Service.execute
```

`RuleMemory` remains the executable verified-rule store. `SkillRegistry` is a separate discoverability index bound to the current RuleMemory fingerprint and every rule/specification/installation hash. Search never installs or modifies a rule.

## Trusted Routing

Structured and controlled-language queries may produce one `EXACT_MATCH` candidate. Even then, dispatch requires an immutable selection receipt with `CONFIRM_SELECTION`. A stale registry, changed RuleMemory, changed receipt, changed candidate list, changed query, inactive rule, or missing confirmation fails closed.

## Assistive Routing

Lexical overlap, character n-grams, BM25, and the learned bi-encoder always return non-exact candidate proposals. Their only next actions are candidate review, clarification, synthesis, or unsupported. Confidence cannot set `exact_match`, write RuleMemory, install a rule, or bypass confirmation.

## Audit Flow

Stage 2 emits `SKILL_QUERY_RECEIVED`, `SKILL_SEARCH_COMPLETED`, `SKILL_AMBIGUOUS`, `SKILL_UNKNOWN`, `SKILL_SELECTED`, `SKILL_SELECTION_CONFIRMED`, `SKILL_DISPATCHED`, and `SKILL_DISPATCH_FAILED`. Events bind hashes instead of duplicating raw request content. A successful dispatch also retains the frozen Stage-1 execution audit and execution hash.

## Runtime Surfaces

- package API: `ai_brain.stage2`
- trusted CLI: `ai-brain-stage2`
- deterministic acceptance: `scripts/m25_skill_registry_acceptance.py`
- research-only retriever: `scripts/m25_learned_retrieval.py`

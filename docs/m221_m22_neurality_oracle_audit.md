# M-22 Neurality / Oracle Audit

| method | trained_parameters | training_dataset | hand_written_score | uses_target_ast | uses_target_semantic_hash | uses_target_sketch | uses_program_from_signature | uses_demonstrations_only | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lexical retrieval | False | none | True | False | False | False | False | False | heuristic |
| embedding retrieval | False | none | True | False | False | False | False | False | heuristic char_ngram_retrieval |
| structured retrieval | False | none | True | False | False | False | False | False | heuristic signature_retrieval |
| sketch completion | False | none | True | True | True | True | True | False | oracle/heuristic |
| grammar-constrained generation | False | grammar | False | False | False | False | False | False | exact symbolic |
| neural-guided search | False | none | True | False | False | False | False | False | heuristic_guided_search |
| execution-guided search | False | grammar | False | False | False | False | False | True | exact symbolic |
| demonstration induction | False | demos | False | True | True | False | False | True | oracle_target_present_metric |
| subprogram planner | False | none | True | False | False | True | False | False | manual symbolic plan |
| learn-once/reuse | False | demos | False | True | True | False | False | True | oracle-selected reuse |
| learned complete-rule retriever | True | contrastive pair data | False | False | False | False | False | False | neural |
| learned candidate scorer | True | positive/hard-negative AST pairs | False | False | False | False | False | False | neural |

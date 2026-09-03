# M-34.4 evaluator isolation

`java_production_evaluator.py` is evaluation-only. It imports the sealed
production representation and compares it with a separately authored javac
manifest. Production modules do not import it, `java_goldens`, evaluation seal
logic, or `tools/m343_java_oracle`.

The enforced order is:

1. ingest source snapshots;
2. run production while the oracle directory is absent and subprocess access
   is denied;
3. seal proposals, trust decisions, evidence, production closure, and candidate
   pack;
4. verify standalone replay without goldens;
5. only then start javac with Java 21, `-proc:none`, and no class execution;
6. seal the independent locations and semantic expectations;
7. compare the immutable production result to the immutable evaluator result.

Tests cover absent, valid, forged, and unreadable oracle directories;
substitution does not alter the production or candidate-pack identity. A forged
golden does alter evaluation. The production API rejects evaluation arguments,
and recursive static-import inspection reports zero forbidden dependencies.

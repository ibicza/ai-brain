# M-33.6g R21 publication-boundary forensics

R21 (`e82083123f78c7ce952303914773e4b5da848ed5`) remains immutable and blocked. Its exact disclosed leak report has report hash `971b41f18c702e656caf3dd9f4076483aad30002c5e1e0b786b638f509d2f728`: two complete encoded-source artifacts plus one host-path artifact, for a total of three.

The source-bearing flow was `compile_provisional_pack` -> `build_java_production_replay_artifact` -> `candidate_pack/java_production_closure.json` -> `load_pack` -> `verify_compiled_java_production_standalone` -> `InstalledDomainRegistry.install`. Both `raw_source_blobs` and `canonical_text_blobs` held 180 complete base64 source bodies. `source_paths` bound the same private replay payload. The legacy evaluator-backed `java_evidence_closure.json` flow is retained only for explicit historical reads; it is not a current public-pack producer.

The host-path flow was `verify_m336_jdk_provider` -> the R21 evaluator -> `evaluation/jdk_provider_receipt.json`. The fields were `java_path`, `javac_path`, and `release_path`.

The sealed machine-readable inventories are under `artifacts/m336g/`. They contain relative code/artifact identities and hashes, never source bodies or absolute paths.

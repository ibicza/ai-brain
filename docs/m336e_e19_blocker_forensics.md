# M-33.6e exact-E19 blocker forensics

## Baseline and immutability

The review started from clean exact E19 `74f7740aea907cd2b4a7e0b885a5d4c60e7aa2db` on branch `exp/stage3-m336e-integration-closed-java-freeze-v4`. The local and remote M-33.6d branch both resolve to E19. The verified first-parent chain is E18 `38082dd1eab82ebfff46ad3c55f5021068909f83` -> R19 `3199c02356de6e7cc9e261504e30f336dd6f09ea` -> F19 `845f65056805acd7517ba4959d38d7d3df8ad7ff` -> H19 `a9527e4731255c4a717cf34e9619ca5c8d07dc66` -> E19.

M-33.6d remains immutable `OUTCOME_C_BLOCKED`. `evaluation/m336d_final_java/e19/independent_evaluation_status.json` confirms that production sealing, candidate-pack compilation, replay, semantic evaluation and installed runtime were not run. The sealed vault and its historical `m336d-fresh-vault-global-v1.selector-invoked` sentinel were read but not modified. No network acquisition was performed.

## Blocker 1: selector authority was consumed before capacity proof

- Caller: `acquire_qualify_select_once`, line 853 of `m336d_final_pipeline.py`.
- Callee: `_select_once`, failed condition at line 1454 and exception at line 1455.
- Input receipt: exact F19 candidate pool; file SHA-256 `ac5e70c3187a7531fda9b06ca1d1225e1bbcb2d1f14d27e35f397737727ebbab`; exact M-33.6d vault manifest; file SHA-256 `c55683161e2090be087e10ae1d1f35b664230048bff807e78a83091f97cbe077`; current E19 disclosure registry with 30 entries.
- Failed condition: fewer than three roots remained ranked after the E19 disclosure-overlap step. The isolated, persistence-free forensic replay observed zero analysis-eligible candidates and raised exact `ValueError: fewer than three qualified roots have callable Java sources`.
- Expected behavior: a production-supported selectability census and exact balanced-capacity proof must complete and be sealed before selector reservation or invocation. An infeasible run must leave both at zero.
- Observed behavior: the historical pipeline wrote the selector sentinel at lines 846-851 before calling `_select_once`. The one allowed invocation was therefore consumed before any capacity proof or selected manifest.
- Graph impact: `_select_once` is called by `acquire_qualify_select_once` and its selector test. The containing pipeline has 34 directly changed graph nodes, 24 depth-two impacted nodes and eight additional affected files.

The physical disclosed vault was also audited independently of E19 freshness overlap. Its five analysis-eligible roots contain 355 files accepted by the old standalone callable predicate (12, 99, 101, 17 and 126). This proves that analysis eligibility, physical callability, run-scoped freshness and production selectability were conflated; the old exception text was not a sufficient capacity proof.

## Blocker 2: incompatible vault path ordering

- Caller: `scripts/m336d_verify_vault_copy.py::main`, line 36.
- Callee: `verify_vault_copy`, lines 897-959 of `m336d_final_pipeline.py`.
- Input receipt: sealed external M-33.6d vault and `evaluation/m336d_final_java/h19/vault_manifest.json`, whose embedded manifest hash is `7cca94dee7c7319097678e32cd5d9d974d83fabfbb9fd6e872737f7687d8dad1`.
- Failed condition: the verifier ordered physical paths by `relative_to(root).as_posix().encode()` while the frozen manifest was built from host `Path` ordering.
- Expected behavior: writer, manifest builder, serializer, portable hasher, local verifier, transfer verifier and platform comparer must share one strict canonical path and unsigned UTF-8 byte ordering primitive.
- Observed behavior: the exact read-only verifier reproduced `all_file_hashes_equal=false`, `tree_hash_equal=false`, `difference_count=1`, while file count and write protection passed. Report hash: `c14035cb6afad62d4a2d7ccd7193f084c467b189790e8ca53eeaa3d2769ebbed`.
- Graph impact: `m336d_contracts.py` has 32 directly changed graph nodes, 22 depth-two impacted nodes and 13 additional affected files; the pipeline impact is recorded above.

## Blocker 3: producer rejected by its own public contract

- Caller/producer: `_acquisition_report`, called at line 856 of `acquire_qualify_select_once`.
- Callee/consumer: `PublicFinalArtifactContractRegistry.validate`; the H19 assembler invokes it for `h19/acquisition_receipts.json`.
- Input receipt: `evaluation/m336d_final_java/h19/acquisition_receipts.json`; frozen contract registry hash `46912eb8b97bfef3090e753ffba16c98de95dc9c34b9914a703a0688b8a6df53`.
- Exact JSON pointer: `/host_audit_hash`.
- Failed condition: the producer emitted `host_audit_hash`, but the acquisition-receipts contract declared no such field. Recursive strict validation raised exact `ValueError: acquisition-receipts contains an unknown nested field`.
- Expected behavior: every real producer variant must canonical-serialize, validate against exactly one typed path contract, round-trip byte-identically and satisfy cross-field invariants before freeze.
- Observed behavior: validation failed before the success assembler could run.
- Graph impact: the contract module has 32 directly changed graph nodes, 22 depth-two impacted nodes and 13 additional affected files.

## Blocker 4: frozen exact-six test contradicted append-only growth

- Caller: `test_disclosed_registry_remains_append_only_and_complete`, lines 392-406 of `test_m336c_spdx_contract_repair.py`.
- Callees: `verify_disclosed_java_registry` and `load_disclosed_java_registry`.
- Input receipt: current E19 registry manifest hash `92b86223d9ad9de4d18e372f4418adf788c4691289ae78c5680c02fa89b05334`, previous manifest `7cbac3b9ce45b697aea4f8be77b7fff9804c395d43631e4676eb9fa71ac3d68a`, 30 current entries.
- Failed condition: test line 395 asserted `len(entries) == 6`.
- Expected behavior: verify the six frozen original identities and bytes as an immutable prefix/subset while permitting only hash-bound append growth.
- Observed behavior: the exact targeted test reproduced `AssertionError: assert 30 == 6` on Windows. The committed Karina log contains the same assertion.
- Graph impact: `java_disclosed_registry.py` has 20 directly changed graph nodes, 39 depth-two impacted nodes and 22 additional affected files.

All four reproductions are diagnostic only. They do not reinterpret the M-33.6d outcome and do not authorize any M-33.6d selector, production or evaluator rerun.

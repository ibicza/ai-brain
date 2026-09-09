# M-33.6k graph impact map

The project-local code-review graph was rebuilt before implementation and used as
the first navigation pass. Concrete callers and behavior were then verified with
source search and tests.

The defect crossed two direct callers of the legacy archive inspector:

- `m336d_final_pipeline._acquire_one` performed the first candidate-local
  inspection;
- `m336e_final_pipeline.run_fresh_acquisition_and_preflight` reopened the stored
  archive and let the second exception escape globally.

R27 adds the following authority path:

- `m336k_archive.inspect_source_archive_v2` produces the single sealed result;
- `m336k_acquisition.acquire_candidate_v2` and
  `recover_disclosed_candidate_v2` attach it to the pipeline item;
- `m336e_final_pipeline.run_fresh_acquisition_and_preflight` consumes that result
  and rejects missing/unbound state;
- `m336k_acquisition.run_candidate_isolated_acquisition` owns terminal accounting
  and the candidate/global exception boundary;
- `m336k_campaigns` exercises archive and mixed-candidate fault surfaces;
- `m336k_run_r27_qualification.py` recovers F26 offline and emits public-safe
  exact-R27 evidence.

The expected blast radius is limited to Stage-3 Maven acquisition, fresh
qualification/census entry, disclosed-registry recovery tooling, and their tests.
Selector, compiler/trust semantics, evaluator thresholds, public-pack contracts,
and tutor/content policy are unchanged.

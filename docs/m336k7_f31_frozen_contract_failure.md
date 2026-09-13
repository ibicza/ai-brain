# M-33.6k.7 F31 frozen-contract failure

F31 (`56c3e489016e054bd7520fa80bc1cb8364112717`) remains an immutable historical `OUTCOME C — BLOCKED`. Its parent is exact Q31 (`49a3ffa6e52be5b1919d39467123c333153e1d4a`), whose parent is the historical implementation tip (`3fc0b9cd10242f9186ab68a97f6fec957908056f`). No H31 or E31 exists.

The first failure was `M336K5 Windows storage preflight failed`. The frozen `resource_budget` component was semantically an observation aggregate, with role `PUBLIC_SAFE_M336K6_RESOURCE_MONITOR_RECEIPT`. The active consumer instead required the obsolete phase-specific field `required_pre_f30_private_storage_bytes`. Because it read that mandatory field using `.get(..., 0)`, the missing field became zero and failed at the storage preflight rather than at strict deserialization.

This first failure was reproduced from a clean detached exact-F31 checkout through the historical hermetic Python launcher and the historical `--validate-only` consumer. The process exited 1 with the same exception, created no validation receipt, and did not invoke the controller. The canonical reproduction request hash is `9d5498a82b671bba1c74cdd64f141fa6451b3a26aa5baaae6547e1d4afdf1688`; its byte hash is `6b33c7b1ab0053620bfa6ce1acc39212ff8dde7d848df4aa1b9f37fe89cbc901`. The captured validate-only output byte hash is `4bc0cfebb742fff114355874e4e572fe7e890bdf2e4d53b5463d599199446d55`.

The exact classifications are:

- `RESOURCE_OBSERVATION_USED_AS_RESOURCE_POLICY`
- `PHASE_SPECIFIC_REQUIRED_FIELD_DRIFT`
- `LEGACY_CAPSULE_RECEIPT_EXPECTED_BY_CURRENT_PREFLIGHT`
- `PERSISTENT_CAPSULE_BINDING_NOT_CANONICALIZED`
- `EXECUTABLE_DEPENDENCY_BINDING_NOT_CANONICALIZED`

The two later, unreached mismatches were already present in committed F31 bytes. The execution capsule bound the persistent public receipt hash where the lower SSH layer required the legacy public receipt hash, and it bound an executable-dependency manifest different from the persistent capsule's verified manifest. Unclassified contract mismatches: 0.

M-33.6k.7 fixes the producer/consumer boundary by separating phase-neutral policy from measured observation, deriving an independent resource gate, and making a canonical persistent-capsule binding set plus an explicit legacy compatibility receipt the only current capsule authority. The historical F30/F31 readers remain unchanged and unreachable from the new V3 current-authority checks.

The F31 failure occurred before any route-ledger write, acquisition reservation, source request, candidate attempt, selector/evaluator reservation, or vault creation. All historical official counters remain zero and the historical vault remains absent.

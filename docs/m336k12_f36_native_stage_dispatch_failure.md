# M-33.6k.12 F36 native-stage dispatch failure

F36 (`2bfd5755a082a63917efdf1ef849351376a115a1`) is preserved as an immutable historical Outcome C. Its one-shot route stopped after `PREFLIGHT_VERIFIED`, `FREEZE_VERIFIED`, and `AUTHORIZATION_VALIDATED`, then appended `FINAL_ROUTE_FAILED`. Acquisition, selection, evaluation, source fetching, and vault creation were never admitted.

The exact F36 producer emitted the first historical private command envelope as:

```text
python executable
arguments = ("-s", "-B", worker, "--request", request,
             "--event", "ACQUISITION_RESERVED", "--receipt", receipt)
```

The exact `M336K5HermeticCommandWorker` consumer required `arguments[0] == "-B"` and extracted the target from `arguments[1]`. The reproduced exception was `M336K2ProtocolError: M336K5 native stage command shape changed`. If only that guard were removed, the consumer would select `-B` as the target. Producer and consumer therefore disagreed on both the target offset (2 versus 1) and the target-argument offset (3 versus 2).

The outer PowerShell/bootstrap chain already owns the real interpreter arguments `-s -B`. They are Layer A interpreter arguments and must not enter Layer C target arguments. In the v5 compatibility envelope, the single leading `-B` is explicitly a `HISTORICAL_COMPATIBILITY_MARKER`; the versioned adapter strips it before dispatching `scripts/m336k2_run_stage.py`.

The side-effect-free reproduction started zero subprocesses, created no native receipt, and wrote no route or acquisition event. The immutable F36 ledger, released F36 reservation receipt, intact unreleased F35 reservation, candidate pool, threshold manifest, persistent capsule, and liveness receipt were not changed.

## Authority map

| Value | Producer | Consumer | Active v5 classification |
|---|---|---|---|
| `M336K5_REQUIRED_INTERPRETER_ARGUMENTS` | startup policy | PowerShell launcher/bootstrap | `OUTER_INTERPRETER_ARGUMENT` |
| `m336k5_launch_python.ps1` | invocation-plan builder | PowerShell | Layer A launcher |
| `M336K5PythonInvocationPlan` | startup builder | stdlib bootstrap | Layer A/B boundary |
| `m336k5_python_bootstrap.py` | launcher | invocation-plan target | `BOOTSTRAP_ARGUMENT` dispatcher |
| `M336K12NativeStageDispatch` | canonical v5 dispatch builder | versioned adapter | Layer C authority |
| `M336K2CommandSpec` | explicit v5 compatibility adapter | `M336K5HermeticCommandWorker` | historical container only |
| `M336K12NativeStagePlanBinding` | v5 plan builder | validate-only/controller preflight | complete-plan authority |
| `M336K12ProducerConsumerParityReceipt` | complete-plan verifier | freeze/admission/controller | parity proof |

The failure is fully classified: the historical F36 producer duplicated Layer A flags into the private Layer C container, while the consumer implemented the older compatible offset contract. No pool, provider, threshold, capsule, environment, or acquisition defect contributed.

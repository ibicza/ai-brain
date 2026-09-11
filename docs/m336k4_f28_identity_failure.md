# M-33.6k.4 historical F28 identity failure

The historical F28 commit `a18ad42702e2197a0076a38e696e525e51c830d4`
is preserved unchanged as **OUTCOME C — BLOCKED**. Its parent is exact Q28
`7ef4c2cfc28019602fa9864f51368b376a096dc1`, whose parent is implementation
tip `4f9cdd68d11dd5dc2568d75e63a24288a5993f2f`. There are no merge commits in
that interval and H28/E28 were never created.

The preserved official route request was an untracked operator-created JSON
object. Its byte SHA-256 is
`cf087e643133148da628ed7cdb6d958e0fc44188af7c01ff7867000f0c44dad3`; its
canonical object hash is
`3c34809b056d6667635833721511a0e91c5835bfc8720d1ed5289042bdb0962b`.
It supplied `route_run_id=m336k2.final-java.route.v1` with mode `FINAL`, while
the controller required `m336k2.final-java.outcome-a.v1`.

The wrong string is absent from the tracked implementation and from the
preserved component/evidence input bundles. No tracked official request builder
existed. The official JSON and its separate stage JSON were assembled outside
Git, and both serialized the same caller-selected string. The CLI loaded the
field and passed it directly through
`route_run_id=request["route_run_id"]` to `run_m336k2_final_controller`. The
exception was `M336K2ProtocolError` at the historical
`src/ai_brain/stage3/acquisition/m336k2_controller.py:214`, with process exit
code 1 and message `M336K2 final run identity is reserved`.

The disposable path did not protect this edge. It rendered separate route and
stage templates, used a disposable rehearsal identifier and mode `REHEARSAL`,
and therefore never loaded the exact official FINAL request value. Q28 bound
the disposable result, but did not execute the later hand-written official
request.

The failure occurred before pre-ledger completion and route context creation.
The immutable historical counts are: controller process invocations 1; route
events 0; acquisition reservations/invocations 0/0; candidate attempts 0;
selector reservations/invocations 0/0; evaluator reservations/invocations
0/0; source-body bytes 0; official vault not created. The blocked receipt hash
is `a057bc22aec599bb26ee9215167c4e094295eb072ac27737f305b9459605935e`.

M-33.6k.4 removes the field from the external request. The protocol run ID is
now derived from independently parsed typed authorization, typed freeze, and a
frozen route-identity bundle by one tracked builder and one loader shared by
disposable and official paths.

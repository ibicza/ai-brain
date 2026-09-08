# M-33.6j R25b graph and boundary review

The graph was rebuilt from exact R25a before implementation. The raw build
indexed 1,108 files, 16,216 nodes, and 113,334 edges; the normalized status
reported 1,107 files, 14,869 nodes, and 111,198 edges. `detect-changes` was
empty before the R25b edits.

The graph search, caller/callee traversal, `tests_for`, and depth-two impact
review identified `scripts/m336i_java_final_route.py::_prepare_karina` and
`::_run_karina_production` as the active large-tree boundary. Their downstream
flow reaches remote materialization, compiler-aware production, replay,
evaluation, runtime verification, and final staging.

All SSH subprocess creation remains centralized in
`m336j_transport.py`. Small schema-bounded JSON uses the bounded in-memory
invocation. Tree upload/download uses `Popen` with file-backed stdin/stdout and
bounded stderr. The Karina worker has no subprocess call site.

Private boundaries are the execution capsule, SSH configuration, storage root,
source vault, selected snapshot, replay root, and streamed temporary archives.
Public boundaries are content-derived capsule/dependency receipts, storage and
command receipts, source-free pack artifacts, typed operation receipts, and the
ordered route transcript. Public objects reject absolute private paths.

The pre-Q25 implementation set includes the transport, storage preflight,
strict schemas/codecs, typed receipt/transcript verifier, mutation battery,
direct remote worker, exact quality runner, F25 freeze builder, final controller,
H25/E25 publishers, commit verifier, and readiness verifier. The future
orchestration manifest resolves these entrypoints and requires zero post-Q25
implementation files.

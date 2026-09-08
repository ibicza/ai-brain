# M-33.6j graph impact map

The code graph was rebuilt from exact F24 in the isolated M-33.6j worktree before broad source inspection. The rebuilt graph contained 14,713 nodes and 109,481 edges and was commit-bound to `4891de1c3a0f6ba2d5d012ab5189dbb5222ba6bd`. Graph status, change detection, symbol search, callers, callees, `tests_for`, and depth-two impact were inspected.

The graph exposes two distinct execution paths:

```text
Q24 quality gate
  -> local sys.executable
  -> local route preflight

F24 Windows final controller
  -> non-interactive SSH shell
  -> bare uv
  -> host-preflight / produce-worker
```

Both `_prepare_karina` and `_run_karina_production` reach `_invoke_karina_worker`. The worker reaches source materialization and compiler-aware production, while the final input validator separately reaches the remote host-preflight command. The old quality gate only covered its local subprocess route, so its passing tests could not establish that the non-interactive SSH shell resolved `uv`.

The affected implementation surface is `scripts/m336i_java_final_route.py`, including `_invoke_karina_worker`, `_prepare_karina`, `_run_karina_production`, `_produce_worker`, `_host_preflight`, and `_worktrees`; the route registry and freeze authorization/manifest builders; the exact-quality runner; host/JDK identity verification; and acquisition, selector, evaluator, and route-state ledgers.

R25 introduces a private execution capsule, public path-free receipt, explicit executable dependency manifest, typed command plan and strict SSH transport, six registered remote route components, and a direct-Python remote entrypoint. Source tree transfer uses canonical archives over bound stdin/stdout rather than ad-hoc `scp`, and remote Git use receives the exact frozen executable handle.

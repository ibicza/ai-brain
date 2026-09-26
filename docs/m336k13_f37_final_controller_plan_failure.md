# M-33.6k.13 F37 final-controller plan failure

F37 (`d90dc54f121cec13ac90131e8f52c4129033c65b`) remains an immutable historical `OUTCOME C - BLOCKED`. Its parent is Q37 (`b6ec1ed93cfc17aa7b6013fd26252ea897be3754`), whose parent is the exact final k.12 implementation tip (`3b718ddc5cbab279da351169cbc39070fe64c50f`). H37 and E37 were not created.

The frozen invocation-plan hash was `830f7f2afe35e5e2079a5ba9338eef150a5f2c2be2c7fdf1d57de8b73bad888c`. The one post-F37 validate-only launch actually loaded a plan with hash `392187cb7b8ed4f0cb1385fc2754becc2721d79bc133243306d1f95d8320888a`. Five top-level plan fields differed: validate arguments, execute arguments, validate startup-receipt destination, execute startup-receipt destination, and the derived invocation-plan hash. All differences are classified; no raw private paths are published.

The live executable verifier correctly rejected the mismatch before preledger creation, reservation release, controller invocation, route events, acquisition, source requests, vault creation, or runtime-root creation. The F37 reservation remains intact and unreleased, with content hash `3d6f9112c19ddac2c105c469799d6289bf9c0d55cec6556a8a476f5edb256484`.

R38a is retained as a bounded shape gate. It closes path agreement, absolute/unique destinations, and rejection of the old F37 plan before stale-output validation. It does not establish immutable plan bytes, actual bootstrap-loaded identity, selected operation/arguments, same-file reuse, or lifecycle immutability. Those predicates remain mandatory work for R38b.

The machine-readable field comparison is in `artifacts/m336k13/f37-final-controller-plan-forensics.json`; the R38a closure inventory is in `artifacts/m336k13/r38a-closure-report.json`.

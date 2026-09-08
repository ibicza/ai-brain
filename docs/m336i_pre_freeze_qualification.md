# M-33.6i authorized final Java pre-freeze qualification

Status: `READY_FOR_FINAL_ACQUISITION`.

Q24 is evidence-only and qualifies exact R24
`1adaf8d38b18714e9c0ff8a4213ca50bb8b5ee16`, whose sole parent is immutable
Q23 `067855a9c3dfdfd503011444f08896d867beceac`. The qualified R24
implementation-tree identity is
`f2ae448c95dd931634b84b73149819a53e64a574e68f997733ab6bfdcb1c3c2d`.
The staged Q24 evidence identity is
`3c5b26473ff99d6e1575c995344eab4aff926f35b0d5f2d19f6b7fbb3f5eca9c`.

The live route registry and route manifest were independently recomputed and
matched the frozen rehearsal evidence. Their hashes are respectively
`1c552c4aed3893252f6eeb71b7a4f2c4497f8be418918605495a2a00da393ec0`
and `7166647a8db1029263820ff6534f7a87ecf1a7228178af3ced69c6ce95903fa7`.
All 19 callables resolved, all 20 route edges were compatible, and the refusal
guard was not registered as the final acquisition provider. The real provider
source and callable-signature hashes are
`e3acfe1c87ecf3d4391053b44fcb63cd88770a57d46d6fb3b0814da27baba53a`
and `9c7e29682e2b63110a5e2e4eb560ca6aa88c57c62645b86930fea2db759fffb2`.

The disclosed regression rehearsal reproduced 180 selected files with root
distribution 19/27/63/18/53, 1,587 proposals, 1,575 trusted and 12 withheld.
Its candidate-pack content, tree, and replay hashes remained exactly
`d30aeb58b441c3c454836692a8f923d03cfae47195ee855ea3078f9c6b74ca0c`,
`720893f00c3264df56c3e1d21d57b0ce70d4e568c99d1f24b011fef0a47bdc7d`,
and `3145879bec1867861f2dac79aaadb95d95dadbd8678dc4a60947d6990003cc51`.
Independent field evidence was exact for all 59,864 expected rows.

The count-neutral rehearsal selected 12 files over three roots with a maximum
root contribution of four and two closure-support files. It produced 11
proposals, 10 trusted and one withheld, with independently evaluated semantic,
location, field, SPDX, runtime, replay, and public-pack gates all passing.

The authorized-provider rehearsal exercised the real acquisition-provider code
path with a generated private fixture. It recorded one rehearsal reservation,
one rehearsal invocation and zero reruns while leaving final reservations and
final invocations at zero. Its two-platform production selected 180 files over
three roots and produced 1,080 independently authorized trusted proposals.

Across all three rehearsals the Windows and Karina platform-neutral candidate
packs, replay commitments, declared field evidence, and production outputs
matched. Every independent evaluation reported zero wrong trusted proposals,
zero field missing/extra/duplicate/wrong rows, zero false automatic SPDX
identities, zero evaluator network/production/selector/materialization calls,
zero synthetic defaults, and zero Torch imports. Trust, location, semantic,
field, SPDX, runtime, pack-integrity, and replay thresholds passed.

Exact R24 quality passed on Windows and Karina. The public receipt hashes are
`35a43d4df9856dc408846aa79090301e5afec39444418d2a4241cc347eaef599`
and `08befe8654245ee6e169a2df21223cf5f43be3b8f204dd0fe0a97df1988bb027`.

Before F24, the independently inspected final state is unspent: acquisition
reservations/invocations 0/0, selector reservations/invocations 0/0, evaluator
reservations/invocations 0/0, route states 0, and new final source-body bytes
0. Source-leak, absolute-path, private-role, unresolved-component,
incompatible-edge, rehearsal-failure, and quality-failure counters are all 0.
The public readiness receipt hash is
`8b997ca7bdb763a4d9d4444ccf19a7e261102012b18de8ea224094744f9824e9`.

This qualification authorizes creation and exact Windows/Karina validation of
F24. It does not itself authorize a network acquisition and does not consume the
one-shot final acquisition.

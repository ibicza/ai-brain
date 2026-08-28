# M-29.1 educational authority

Runtime user authority and offline answer-key compilation are separate.

Runtime new calculations follow request -> proposal -> PREPARED -> explicit confirmation -> execution -> COMPLETED. Precompiled explanations and exercise presentation execute no chemistry tool. Runtime modules do not import the compiler.

The only educational direct call to `ChemistryToolRegistry.execute()` is in `src/ai_brain/stage2/education/compiler.py`. It requires `ActorIdentityType.TRUSTED_PROCESS`, identity `m291-verified-answer-key-compiler`, an allowlisted tool, canonical immutable arguments, the current manifests and a receipt-bound audit event. MODEL, USER and blank identities fail closed.

Development instrumentation measured presentation 0, precompiled explanation 0, unconfirmed new explanation 0 and confirmed new explanation exactly 1 execution. Runtime network, Torch authority, FactMemory writes and RuleMemory writes are absent.

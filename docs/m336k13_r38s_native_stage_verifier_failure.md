# M-33.6k.13 R38s native-stage verifier failure

At exact Q38R `ee34ca2bb9e90bbcb5a916af51fefbdffe375158`, the fresh side-effect-free reproduction terminated with `M336K12 live plan binding changed`.

The last successful semantic operation was `M336K13NativeStagePlanBinding.verify`. The failing equality compared the active v6 `M336K13NativeStagePlanBinding` directly with a reconstructed v5 `M336K12NativeStagePlanBinding`; their schema, role, active hash and final-controller extension necessarily differ.

The reproduction output SHA-256 was `668c6280faeda66ee7b1623aae1cc2860b743d83c35e16c50cc5d8eade61938f`. Route, acquisition, selector and evaluator events; source requests; candidate bodies; official vault files; reservation releases; and plan writes were all zero. No raw private path is published here.

The repair uses one exact internal v6-to-v5 projection for the unchanged complete v5 verifier, then rebinds only the active native-stage hash and dependent parity receipt hash. The projection is never serialized as active authority.

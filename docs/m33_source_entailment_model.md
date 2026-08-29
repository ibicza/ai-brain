# M-33 source-entailment model

The acquisition state machine distinguishes syntax, structure, evidence, and
installation authority:

- `PARSED`: syntax recognized.
- `STRUCTURE_VERIFIED`: typed IR validates but field evidence is incomplete.
- `SOURCE_ENTAILED`: every required leaf dereferences exact source bytes.
- `CROSS_SOURCE_CORROBORATED`: independent sources entail the same normalized
  claim.
- `REVIEW_REQUIRED`, `CONFLICT`, `NEEDS_NEW_CAPABILITY`, and `REJECTED`: explicit
  conservative outcomes.
- `APPROVED`: an exact verifier or legitimate reviewer authorized installation.

Source entailment means only “this source explicitly states the normalized
value.” It is not universal truth. The automatic approval actor is the named
trusted process `m33.exact-source-entailment-verifier.v1`; it never claims to be
a human. Narrative interpretation, causality, ambiguity, and incomplete
evidence cannot use that approval route.

Corroboration requires distinct source documents. Conflicts remain explicit and
block trusted answers. Unsupported knowledge kinds and missing capabilities
fail closed without content-policy or moral refusals.

# Manual Mapping Policy

`REVIEWED_MANUAL_MAPPING` means that authority bytes are fixed and cited, while selected fields are entered or mapped through a human-reviewed fixture. It is not deterministic extraction.

An approval binds the official snapshot, exact fields and values, locators, mapping hash, policy version, reviewer identity/type, decision, and timestamp. Approval requires a nonblank human reviewer; `MODEL` is forbidden. Any input change invalidates the approval and derivation.

IUPAC identities and BIPM mole fields use this policy. RU names instead use `POLICY_TRANSFORMATION`, because they are a local representation policy rather than an authority-extracted factual table.

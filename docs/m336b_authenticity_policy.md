# M-33.6b artifact authenticity policy

Strong modes are `SHA256_SIDECAR_VERIFIED`, `OPENPGP_SIGNATURE_VERIFIED`, `IMMUTABLE_SCM_CONTENT_EQUIVALENCE`, and `MULTI_CHANNEL_VERIFIED`. `REPOSITORY_TLS_ONLY` is not automatically eligible.

A downloaded detached signature is recorded as `PRESENT_UNVERIFIED`; it grants no authority. OpenPGP authority would require successful cryptographic verification, an exact frozen key fingerprint, frozen key provenance, and a verification receipt. M-33.6b freezes no such signer policy, so signature availability alone cannot upgrade a candidate.

Complete immutable-SCM correspondence is strong only when every Java archive entry is accepted by the frozen correspondence policy with zero unmatched and zero ambiguous entries.

# M-32 compiler security report

The acceptance battery rejects malformed UTF-8, duplicate JSON keys, active/hidden HTML, external active references, active PDF content, oversized resources, symlinks, hash substitution, source-span mismatch, provider path escape, capability downgrade, assistive self-verification, and model self-approval.

Prompt-injection phrases, fake approval JSON, internal-receipt claims, and shell-looking text in ordinary source have no authority. They remain text unless they match a bounded descriptive grammar; executable expressions reject code/functions.

Trusted CLI imports no `torch`, performs no runtime network access, and prints only public identifiers/hashes by default.

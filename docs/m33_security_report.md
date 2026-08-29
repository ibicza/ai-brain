# M-33 security report

All 25 snapshots remained inert data. No source approved or installed itself,
wrote FactMemory/RuleMemory, executed code, or changed a registry. The frozen
security test preserved fake approval text and shell text as data, stripped
active script content, rejected an off-seal domain, and verified schema mismatch
returns `NEEDS_NEW_CAPABILITY`.

The real corpus scan found 325 non-ASCII characters, 311 equation-shaped lines,
286 unit mentions, three documentation warnings/deprecations, and two retained
URLs. It found zero compiler annotations, fake JSON approvals, fake receipts,
prompt-injection phrases, or shell-command examples. Maximum source line size
was 1,483 UTF-8 bytes. Therefore the real corpus did not exercise every requested
adversarial category; this is reported as a coverage limitation, not a pass by
construction.

Runtime was re-run with sources and goldens physically moved out of the
workspace. All 500 outputs remained identical in status, proving the installed
pack path has no source/golden shortcut. A socket-disabled runtime query passed,
made zero network calls, and did not import torch.

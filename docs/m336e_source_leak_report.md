# M-33.6e source leak report

The final leak gate scans every new Git object reachable after E19. It rejects
source-JAR and SCM archive bytes, complete Java files, 256-byte source windows,
base64 or hexadecimal source encodings, raw legal-document text, and local
vault paths. Raw acquisition bytes remain in the external sealed vault.

H20 assembly consumes only a hash-bound leak report whose aggregate fresh-source
leak count is zero. Contract validation independently rejects archive payloads,
source excerpts, credentials, and host absolute paths. E20 readiness rechecks
the H20 seal and the primary leak denominator.

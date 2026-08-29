# M-32 source artifact model

`SourceBundle` contains immutable `SourceDocument` records and an acquisition manifest. A document binds media type, language, exact byte hash, canonical-text hash, source metadata, import time, version, parent bundle, bounded structure, and document hash.

The acquisition store is content-addressed. Blob reads rehash bytes, object paths bind canonical object hashes, collision simulations fail, and backup/restore re-verifies every object.

Trusted inputs are local UTF-8 text, Markdown, static sanitized HTML/Javadoc, strict JSON, and bounded text-layer PDF. Runtime network, OCR, JavaScript, macros, and archive extraction are disabled.

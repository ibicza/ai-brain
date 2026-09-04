# Maven provenance provider

The provider constructs locations only from a validated coordinate and frozen `https://repo.maven.apache.org` repository. It binds sources JAR/POM bytes, SHA-256 sidecars where published, detached-signature presence, final URL, redirect chain, media type, content length, and a network receipt. TLS alone is not treated as complete provenance.

POM parsing forbids DTD/entity input, verifies exact effective GAV (including parent fallback), rejects duplicate metadata, and never follows a network location found in POM text. HTTP downgrade, host substitution, redirect escape, classifier substitution, version substitution, checksum mismatch, and content-length mismatch fail closed.

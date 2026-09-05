# M-33.6e producer-contract compatibility

Contract v2 declares twelve canonical H20/E20 JSON producers and thirty-six
success, blocked, and review-required variants. Each gate case invokes the real
producer, uses the real canonical serializer, validates a unique path contract,
strictly deserializes, reserializes, and requires byte equality.

Recursive contracts reject unknown fields, wrong nested types, duplicate JSON
keys, wrong schema versions, embedded source/archive payloads, source excerpts,
credentials, and host absolute paths. Cross-field checks bind content hashes and
verify acquisition, selector, registry-append, and readiness denominators.

The M-33.6d failure at `/host_audit_hash` is closed by an explicit SHA-256 field in
the acquisition-receipts v2 contract. The immutable v1 registry remains available
only as a read-only legacy adapter; v2 is not widened with free-form fields.

# M-33.6a limitations

This is development repair, not a fresh-freeze result. Maven detached signatures are fetched and byte-bound when present; signer trust/key discovery is not claimed. Maven Central does not publish SHA-256 sidecars for every historical component, so absence is recorded rather than converted into a false checksum claim. POM parent/effective-model resolution remains explicit evidence, not an implicit network walk.

No new coordinate pool, selector seed, untouched source JAR/tree, final evaluator, or F/H/E freeze was created. Only the already disclosed Guava 33.4.8-jre, Commons Collections 4.5.0, Caffeine 3.2.0, and local adversarial fixtures were used.

Roadmap: M-33.6a repairs M-33; M-33.6b is the next untouched Java freeze; M-33.7 remains the final four-domain proof; roadmap M-34 Episodic and Relationship Memory has not started. No moral, moderation, NSFW, political, ideological, refusal, topic, personality, opinion, internal-reasoning, or answer-censorship policy was added.

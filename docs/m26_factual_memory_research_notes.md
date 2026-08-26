# M-26 Factual Memory Research Notes

## Scope

The review selected small, enforceable ideas for a CPU-only factual memory. It does not claim full PROV, SQL:2011 temporal support, RDF, probabilistic truth maintenance, or automatic entity linking.

## W3C PROV

Primary sources: [PROV-DM](https://www.w3.org/TR/prov-dm/), [PROV Constraints](https://www.w3.org/TR/prov-constraints/), and the [PROV primer](https://www.w3.org/TR/prov-primer/).

1. Authoritative model: entities, activities, agents, usage, generation, derivation, revision, attribution.
2. Provenance: a source snapshot, evidence span, proposal, approval, and claim are different entities linked by activities.
3. Temporal model: generation/use/activity time, not a replacement for bitemporal database semantics.
4. Conflict behavior: PROV describes derivation; it does not decide which conflicting claim is correct.
5. Update/retraction: a revision is a new entity. Earlier entities remain addressable.
6. Query semantics: provenance is returned with the claim, not reconstructed from prose.
7. Exact: hashes, source/evidence links, approval dependencies, revision identity.
8. Assistive: future mapping to full PROV-O/PROV-N.
9. ai-brain idea: preserve source, snapshot, evidence, proposal, reviewer, and claim as distinct immutable records.

## Bitemporal Databases

Primary sources: Jensen and Snodgrass' [bitemporal interval definition](https://www.cs.arizona.edu/~rts/pubs/TRmerged.pdf) and Torp, Jensen, and Snodgrass on [effective timestamping](https://www.sigmod.org/publications/dblp/db/journals/vldb/TorpJS00.html).

1. Authoritative model: valid time is when a fact applies in the modeled world; transaction time is when the database held that belief.
2. Provenance: recording time is system-controlled and independent of source publication time.
3. Temporal model: orthogonal valid and transaction intervals; M-26 uses half-open valid intervals.
4. Conflict behavior: overlap is evaluated on valid time under the predicate's conflict key.
5. Update/retraction: append transaction events; do not overwrite historical assertions.
6. Query semantics: `VALID_AT`, `KNOWN_AT`, and their conjunction.
7. Exact: interval boundaries, timezone normalization, visibility at transaction time.
8. Assistive: natural-language interpretation of temporal questions.
9. ai-brain idea: explicit valid fields plus append-only status/relation events.

## Truth Maintenance

Primary sources: Doyle's [A Truth Maintenance System](https://doi.org/10.1016/0004-3702(79)90008-0) and de Kleer's [An Assumption-Based TMS](https://doi.org/10.1016/0004-3702(86)90080-9).

1. Authoritative model: beliefs retain justifications and dependencies.
2. Provenance: reasons for a belief remain inspectable.
3. Temporal model: not intrinsically bitemporal.
4. Conflict behavior: inconsistent alternatives may coexist rather than being erased.
5. Update/retraction: dependency changes alter belief state while preserving reasons.
6. Query semantics: explain why a claim is supported or affected.
7. Exact: evidence dependencies and explicit retraction propagation.
8. Assistive: future policy for selecting among resolved alternatives.
9. ai-brain idea: source retraction marks dependent claims `AFFECTED`; it does not delete or silently resolve conflict groups.

## Temporal Knowledge Graphs

Primary source: [Bitemporal Property Graphs to Organize Evolving Systems](https://arxiv.org/abs/2111.13499).

1. Authoritative model: graph relations carry temporal metadata.
2. Provenance: graph edges still require external source/evidence identity.
3. Temporal model: evolving graph state can be queried across two time axes.
4. Conflict behavior: graph topology alone does not supply a trustworthy winner.
5. Update/retraction: preserve versions and temporal edges.
6. Query semantics: time-sliced traversal.
7. Exact: temporal filtering and claim identity.
8. Assistive: graph search or learned completion.
9. ai-brain idea: keep relational SQLite authoritative now; add graph projections later, never the reverse.

## Entity Resolution

Research reference: [Almost all of entity resolution](https://pmc.ncbi.nlm.nih.gov/articles/PMC11636688/) and Ji et al.'s [Entity Linking survey](https://doi.org/10.1109/TKDE.2021.3059783).

1. Authoritative model: records/mentions and candidate entities are distinct.
2. Provenance: every alias belongs to an explicit entity record.
3. Temporal model: entity lifecycle is metadata in M-26, not automatic identity evolution.
4. Conflict behavior: aliases shared by several records are ambiguous.
5. Update/retraction: deprecate records explicitly; never fuzzy-merge silently.
6. Query semantics: exact ID, normalized canonical label, or normalized alias.
7. Exact: normalization and ambiguity result.
8. Assistive: fuzzy candidate generation only.
9. ai-brain idea: fail with `AMBIGUOUS_ENTITY` whenever exact alias lookup is non-unique.

## Evidence Addressing and Content Integrity

Stable standards: [RFC 6901 JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) and [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final).

1. Authoritative model: byte/character spans or RFC 6901 pointers into immutable snapshots.
2. Provenance: snapshot and selected excerpt each have SHA-256.
3. Temporal model: retrieval time belongs to SourceRecord.
4. Conflict behavior: evidence may `SUPPORT` or `CONTRADICT` a claim.
5. Update/retraction: changed content is a different snapshot; source status is an append-only event.
6. Query semantics: evidence is re-extracted and re-hashed before trusted use.
7. Exact: digest, span bounds, pointer escaping, UTF-8 decoding.
8. Assistive: future document extraction proposals.
9. ai-brain idea: content-addressed blobs with no network access in the trusted core.

## SQLite

Primary documentation: [WAL](https://www.sqlite.org/wal.html), [Online Backup API](https://www.sqlite.org/backup.html), [PRAGMA integrity_check/application_id/busy_timeout](https://www.sqlite.org/pragma.html), and [atomic commit](https://www.sqlite.org/atomiccommit.html).

1. Authoritative model: constrained relational tables and transactions.
2. Provenance: foreign keys preserve source-evidence-claim relationships.
3. Temporal model: indexed explicit columns and append-only event tables.
4. Conflict behavior: schema-driven conflict groups are normal rows.
5. Update/retraction: single-writer `BEGIN IMMEDIATE`; rollback leaves no partial graph.
6. Query semantics: parameterized indexed SQL.
7. Exact: foreign keys, `synchronous=FULL`, integrity check, application ID, hash chain.
8. Assistive: none in the storage core.
9. ai-brain idea: SQLite plus canonical export, because a physical file hash alone is not a logical snapshot identity under WAL.

## Decision

M-26 combines a PROV-inspired object separation, classic bitemporal visibility, truth-maintenance-style dependency retention, exact entity lookup, content-addressed evidence, and transactional SQLite. Confidence remains decomposed metadata. No learned score creates truth, removes a conflict, or authorizes a write.

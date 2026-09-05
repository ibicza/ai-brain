# M-33.6e persistent protocol ledger

`RunProtocolLedger` is canonical UTF-8/LF JSONL outside Git. Every event is
hash-chained and binds protocol version, exact freeze subject, acquisition run,
candidate pool, and the monotonic vault/qualification/census hashes as they become
available.

The only valid order is freeze verification, one acquisition reservation and
completion, vault seal, qualification, census, one selector reservation and
completion, Windows seal, Karina seal, evaluation reservation, and evaluation
completion. Exclusive lock creation and durable append make process restarts
fail closed. A consumed selector reservation cannot be repeated; evaluation
cannot be reserved before both production seals.

Git stores only `RunProtocolLedgerReceipt`, which exposes bound ledger bytes/hash
and authoritative counts. Disclosed rehearsal and final fresh acquisition use
different run IDs and different external ledgers.

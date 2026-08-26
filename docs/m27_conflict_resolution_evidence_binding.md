# M-27 Conflict Resolution Evidence Binding

Manual resolution now persists typed `ResolutionEvidenceLink` rows. `SUPPORTS_REMAINING` must be SUPPORTS evidence attached to a retained claim. `CONTRADICTS_REMOVED` must be CONTRADICTS evidence attached to a removed claim. `SUPPORTS_DISMISSAL` is available only for a safe dismissal that retains every claim.

Links bind evidence, claim, role, and hash. Verification checks event/link equality, group membership, partition role, immutable evidence polarity, and attachment. Unrelated evidence, changed polarity, empty manual partitions, selected/remaining mismatch, and dismissals that remove candidates fail closed.

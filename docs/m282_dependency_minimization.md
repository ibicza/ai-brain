# Dependency Minimization

Knowledge snapshots are built from operation-specific requirements, avoiding domain-wide invalidation by unrelated sources.

| Operation | Required knowledge | Explicitly unrelated |
|---|---|---|
| Molar mass / mass-amount | CIAAW atomic weights | RU policy, BIPM |
| Entity-count conversion | BIPM Avogadro constant | CIAAW when no molar mass is needed |
| Formula composition | Parsed formula only | All factual sources |
| English identity | IUPAC identity | RU policy |
| RU name | IUPAC identity and RU policy | BIPM, CIAAW |

Acceptance verified eight dependency cases: molar mass does not depend on RU or BIPM, Avogadro conversion does not depend on CIAAW, and atomic-weight lookup does not depend on BIPM. Unrelated source-state changes therefore do not stale otherwise valid results.

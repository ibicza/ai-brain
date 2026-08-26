# M-26 FactValue Types

| Kind | Canonical storage | Main rejection rules |
|---|---|---|
| STRING | UTF-8 text | non-text |
| INTEGER | canonical base-10 text | bool, malformed integer |
| DECIMAL | normalized Decimal text | float, NaN, infinity |
| BOOLEAN | JSON boolean | non-bool |
| DATE | ISO `YYYY-MM-DD` | malformed date/datetime |
| DATETIME | UTC ISO with `Z` | missing offset |
| ENTITY_REF | validated entity ID | malformed/missing entity |
| QUANTITY | Decimal + canonical unit | missing/invalid unit |
| ENUM | validated symbolic ID | malformed symbol |

Floats are forbidden in trusted artifacts. Canonical JSON is sorted, compact, UTF-8, and deterministic.

# Element Symbol Case Policy

Element symbols match `[A-Z][a-z]?` exactly. They are identifiers, not
case-insensitive aliases. Thus `Co` is cobalt while `CO` is carbon-oxygen in a
formula and ambiguous/not cobalt in a fact query. `co`, `NA`, `CL`, and `FE`
are not accepted as symbols.

English and Russian element names remain case-insensitive reviewed aliases.
The resolver first applies exact-symbol policy, then localized names. Generic
aliases cannot override a wrong-case symbol-like token.

The same resolver policy is used by structured facts and controlled RU/EN
queries; the formula parser independently preserves chemistry symbol case.

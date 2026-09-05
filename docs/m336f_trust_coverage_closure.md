# M-33.6f trust precision and coverage closure

The generic repair adds selected internal compilation closure, correct Java 21 exported-package inventory, inherited/nested type resolution and exact compiler-diagnostic scoping. It contains no family, path, proposal or golden-ID exception.

The latest non-authoritative disclosed development evaluation has 1,575 correct trusted, zero wrong trusted, one correct withheld and 70 incorrect withheld. Trust precision is `1.000000`; recall, legacy coverage and safe coverage are all `0.957447`. All five source-root holdouts have zero wrong trusted and precision `1.000000`.

The evaluator-only opportunity report records all 70 expected-supported withheld locations without influencing production; its report hash is `fb323c5f06dfec2708faf6f20818930e9658c6abf83d74cff9ea8ae2495f6988`. Location and semantic precision are `1.000000`; both recalls are `0.964156`.

These numbers exceed the mandatory `0.850000` and preferred `0.875000` margins, but they do not become qualification evidence until rerun from a clean exact R21 on Windows and Karina.

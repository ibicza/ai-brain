# M-33.6f declaration diagnostic binding

Every compiler diagnostic binds the compilation-run hash, SourceEntryId, source-unit identity, diagnostic code/category, one-based UTF-16 location, canonical UTF-8 position/span, zero or more declaration IDs, scope and binding hash. Trust decisions bind the compiler report, the complete diagnostic-binding hash set, the compilation policy and the applicable blocking diagnostic hashes.

Header diagnostics block their callable. Enclosing-type diagnostics block callables on that receiver. Body-only and unrelated-member diagnostics do not spread to another declaration. Unknown scope on a known unit blocks all automatically trusted callables in that unit; an unbound unit or malformed compiler output blocks the batch. Compiler identity drift fails verification.

Tests cover ASCII, Cyrillic, composed/decomposed Unicode, non-BMP columns, LF/CRLF, tabs, annotations, generics, bounds, records, compact constructors, nested types and overloaded callables. Duplicate compiler basenames are resolved by canonical payload/location evidence or remain explicitly unbound.

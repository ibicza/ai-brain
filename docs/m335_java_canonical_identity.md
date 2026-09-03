# M-33.5 Java canonical callable identity

`JavaCanonicalCallableIdentity` schema 1 binds the frozen Java release hash,
module or `UNNAMED`, binary receiver (nested owners use `$`), `METHOD` or
`CONSTRUCTOR`, exact member name or `<init>`, ordered erased JVM parameter
descriptor, source/classpath scope and its identity hash.

Return type, generic bounds and varargs spelling are semantic fields, not Java
overload discriminators. Varargs use the array descriptor. Identity is
case-sensitive, Unicode-exact after the frozen path policy, independent of
proposal ordinal, absolute root and presentation aliases. Unresolved types have
no canonical callable identity and cannot enter production trust.

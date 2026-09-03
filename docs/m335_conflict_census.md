# M-33.5 conflict policy and census

The H13 census contains 48/48 classified historical instances and zero
unclassified instances. They were false conflicts caused by the unresolved
descriptor sentinel.

The new policy keeps distinct canonical parameter descriptors as legal
overloads. Duplicate physical derivation is blocked. Same canonical identity and
same content from different sources is withheld deterministically rather than
duplicated. Different content is a semantic conflict and withholds all members.
The same runtime binary key across roots is a classpath collision and has no
silent winner. Every withholding reason is emitted before final trust.

# M-33.6e cross-platform report

Three independent equality gates are required.

1. The disclosed M-33.6d vault must have zero physical, canonical-manifest, and
   portable-tree differences between Windows and Karina.
2. Fresh post-F20 vault transfer must have the same three zero denominators.
3. Platform-independent production and independent-evaluation artifacts must be
   byte-identical, with all semantic fields equal.

All vault tools share `CanonicalVaultPath` and unsigned UTF-8 byte ordering.
Physical traversal proves completeness and hash equality only; it does not
define the portable tree. Exact measured hashes and counts are added in Q20,
H20, and E20 and are not asserted by the R20 implementation commit.

`m336e_compare_production.py` compares every production artifact except an
explicit closed set of host-bound execution, performance, state, process, file
access, seal, and summary receipts. In particular,
`m336e_production_execution.json` deliberately binds `platform` and its derived
seal hash, so it is not byte-neutral. The comparator still fails closed on any
difference in production output, trust closure, component manifest, candidate
pack, compilation, or replay artifacts and reports the excluded filenames.

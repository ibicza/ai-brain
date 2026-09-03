# M-34.4 frozen final source selector

The F13 selector targets Java 21 and allowlists immutable Apache Commons Lang
3.17.0, Commons Collections 4.5.0, and Commons IO 2.18.0 source archives from
Maven Central. Their required license is Apache-2.0. Final execution must use at
least two independent roots.

Only `.java` source with callable class, interface, enum, record, or annotation
type declarations is eligible. Generated, vendor, test/tests, module-info, and
package-info paths are excluded. Exact bytes in the prior/development hash
denylist are excluded. Selection is the ascending SHA-256/content-hash rank of
`F13 SHA + family ID + relative path`, bounded to 240 files and 16 MiB. The F13
SHA is part of the seed and the selection is run exactly once.

Frozen final minimums are 60 callable files, 1,500 callable targets, 150 receiver
types, 12 packages, 100 overload groups, 50 constructors, 100 generic methods,
100 throws declarations, and 25 nested-member targets. The selector policy is
frozen here; selected paths, hashes, bodies, target census, goldens, outputs, and
results are deliberately absent from F13.

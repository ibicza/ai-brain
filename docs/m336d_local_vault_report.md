# M-33.6d local vault report

The sealed local-only vault contains 24 candidate directories, 4,469 files, and 4,390 Java files. All files were write-protected before selection. Raw source bodies remain outside Git.

The physical cross-platform comparison found zero byte differences and the same portable byte-sorted tree hash on Windows and Karina: `e8d6eae2b740643d4a77277e9b165d2bdfe308ea80cad30fad87eea244102150`.

The frozen verifier nevertheless reports FAIL on both platforms. Its manifest builder uses host `Path` ordering while its verifier uses raw POSIX-relative byte ordering, producing a deterministic path-order mismatch. The Windows manifest-order tree hash is `01458be4d7730a4662ca4fbe016a0705b2d8c079be70145d6962e7bfe834d1e0`; this is not a physical-byte divergence.

# M-34.1 Java development corpus

`real/java-time/` contains 21 unmodified Java source files from the local OpenJDK 22 `src.zip`, module `java.base`, package `java.time`. OpenJDK source is licensed under GPLv2 with the Classpath Exception; the original per-file notices are preserved.

`synthetic/` contains development-only adversarial fixtures authored for M-34.1. Neither directory contains the M-33 `java.util` final sources, and evaluation checks hash disjointness against the sealed M-33 source-receipt hashes without reading those sources.

# M-34.4 Java release consistency

The sole frozen target is Java 21. `JavaReleaseIdentity` binds all of the
following to 21: source compatibility, javac `--release`, ct.sym, symbol
inventory, module/export model, oracle, optional diagnostics provider, and
evaluation configuration.

The release identity also binds the packaged Java 21 inventory hash. Verification
rebuilds that inventory and rejects any changed field or hash. The pre-freeze
gate requires a PASS report, and a Java-25 substitution mutation must block.

The development corpus uses Jackson 2.18.2 plus untouched `Arrays.java` and
`Map.java` from the exact Microsoft OpenJDK 21.0.11 source archive. OpenJDK 25
M-34.3 package metadata is not treated as Java 21 callable evidence.

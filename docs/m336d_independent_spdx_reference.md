# M-33.6d independent SPDX reference

`tools/spdx-reference-java` is a JDK-21-only evaluator. It has its own strict UTF-8 decoder, NFC/line normalization, lexical normalization, secure XML interpreter, template matcher and receipt hash. Static isolation finds zero dependencies in either direction between it and the Python production matcher; `jdeps` reports only `java.base,java.xml`.

The shared immutable inputs are the official SPDX 3.28.0 XML/text snapshot and case bytes. Classpath-exception-2.0 is bound to SPDX XML commit `6f2ddc538acb19180f4c8e96cff94ccf27822e8b` and license-data commit `c4a7237ec8f4654e867546f9f409749300f1bf4c`.

The disclosed differential corpus has 10,800 cases across six templates, normalization/optional/replaceable variants and substantive/control attacks. Windows and Karina both produced agreement `1.000000`, false automatic identities 0, optional variants rejected 0, substantive mutations accepted 0 and multiple-match automatic acceptance 0.

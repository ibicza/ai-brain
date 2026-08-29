# M-33 Java results

- OpenJDK JDK 21 GA at commit `890adb6410dab4606a4f26a942aed02fb2f55387`.
- 55,087 words, 8 related `java.util` types, 10,660 segments.
- 883 API-shaped proposals; 832 reached `SOURCE_ENTAILED` and 51 remained
  `STRUCTURE_VERIFIED`.
- 4,944/4,995 required field leaves had exact evidence (98.98%).

The frozen independent evaluator joins a proposal by its first source segment.
For API proposals that segment is the type-context line, while the golden is
located at the signature line. It consequently reported 832 wrong automatic
items, proposal precision 0, and source-entailment precision 0. This is a final
black-box failure and was not repaired after F12. No Java proposal was installed.

The executable abstention pack hash is
`d206955b9695e7d1be87fc6abcda9c23092b05a560002bf2554329a6cd3bb51d`.
All 125 runtime tasks produced expected abstentions or
`NEEDS_NEW_CAPABILITY`/`VERSION_MISMATCH`, including compile/run requests.

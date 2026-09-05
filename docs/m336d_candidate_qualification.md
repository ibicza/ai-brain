# M-33.6d candidate qualification

All 24 candidates received ten typed decisions. Five roots are analysis-eligible, covering 410 Java entries: `errorprone-annotations` (28), `failsafe` (103), `jctools-core` (112), `jetbrains-annotations` (31), and `modelmapper` (136). These five permit derived-pack and metrics publication; all 24 deny raw-source and source-excerpt publication.

| Family | Decision | Eligible entries | SCM | Scoped license / reason |
|---|---:|---:|---|---|
| agrona | INELIGIBLE | 0 | INCOMPLETE | REVIEW_REQUIRED; 3 unknown-role legal documents |
| animal-sniffer | INELIGIBLE | 0 | INCOMPLETE | malformed Java encoding |
| byte-buddy | INELIGIBLE | 0 | INCOMPLETE | REVIEW_REQUIRED; 5 unknown-role legal documents |
| checker-qual | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 1 unknown-role legal document |
| classgraph | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 2 unknown-role legal documents |
| dagger | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 17 unknown-role legal documents |
| disruptor | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 1 unknown-role legal document |
| errorprone-annotations | ELIGIBLE_FOR_ANALYSIS | 28 | COMPLETE | RESOLVED Apache-2.0 |
| failsafe | ELIGIBLE_FOR_ANALYSIS | 103 | COMPLETE | RESOLVED Apache-2.0 |
| fastutil | INELIGIBLE | 0 | INCOMPLETE | REVIEW_REQUIRED; 1 unknown-role legal document |
| hdrhistogram | INELIGIBLE | 0 | INCOMPLETE | REVIEW_REQUIRED; no resolved scoped expression |
| java-semver | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; no resolved scoped expression |
| jctools-core | ELIGIBLE_FOR_ANALYSIS | 112 | COMPLETE | RESOLVED Apache-2.0 |
| jetbrains-annotations | ELIGIBLE_FOR_ANALYSIS | 31 | COMPLETE | RESOLVED Apache-2.0 |
| jopt-simple | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; no resolved scoped expression |
| lz4-java | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 1 unknown-role legal document |
| mapstruct | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 3 unknown-role legal documents |
| modelmapper | ELIGIBLE_FOR_ANALYSIS | 136 | COMPLETE | RESOLVED Apache-2.0 |
| moshi | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 2 unknown-role legal documents |
| objenesis | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 2 unknown-role legal documents |
| pcollections | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; no resolved scoped expression |
| reactive-streams | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; no resolved scoped expression |
| roaringbitmap | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 2 unknown-role legal documents |
| zstd-jni | INELIGIBLE | 0 | COMPLETE | REVIEW_REQUIRED; 3 unknown-role legal documents |

The inventory found 94 legal-document candidates. Its strict `unclassified` counter is zero, while 43 documents retain the distinct `UNKNOWN_LICENSE_DOCUMENT` role and correctly force REVIEW_REQUIRED. Nineteen candidates have complete SCM correspondence and five are incomplete.

# M-33.6b final source inventory

Outcome: `OUTCOME_C_BLOCKED`.

The one permitted global acquisition ran on Windows at exact F17
`cd5ffa4bdbc6ef40e702e3315515d87557e586c9`. It downloaded all six frozen,
optional candidates and registered every candidate as disclosed. The sealed
bundle contains 38 files and has tree hash
`52e9f90c4d74dd3b2aa5104afb02917a261c9b1eed49ffb4e8cb8fcf23f8f7a0`.
Windows and Karina independently verified those same bytes.

| Candidate | Coordinate | Frozen license result | Source JAR SHA-256 | POM SHA-256 | Immutable SCM commit | Qualification |
| --- | --- | --- | --- | --- | --- | --- |
| Jackson Databind | `com.fasterxml.jackson.core:jackson-databind:2.20.0` | `EMBEDDED_EXACT_LICENSE` / Apache-2.0 exact | `e192ebfb2a0d705121cfff7419c4d28b9cf589bf52ca8e5cbe83de990c54f10b` | `cefefed01dd2c0d96a88e101bb3e065fc150063b498e301a938c690b02bcf3ce` | `4260f88180e5e45f3be1a290114e55c042bb2213` | `ELIGIBLE` |
| Gson | `com.google.code.gson:gson:2.13.2` | `POM_DECLARATION_ONLY` / Apache-2.0 declaration | `058974b69cb7b0a04712278e11870e84ee8cd8fb5f551bd8401e72ba6638bfef` | `3aa06aa7c0f9af092961a42d09578e4324be146348a0ee6ed47857f7c2677b76` | `686fad782d969d8f15c7581a5435a208b810caa7` | `REVIEW_REQUIRED` |
| Apache HttpCore5 | `org.apache.httpcomponents.core5:httpcore5:5.3.6` | `CONFLICTING_LICENSE_EVIDENCE` | `08dbcd68ee403e432554010e38c2eae2b6c97ce3ed5e0af8e11679870c8f141c` | `8e37043c6fc40289fe3f0cafd33d0d7e1a10ace4f74495bbc5be39586614718f` | `1c15f3c85cb9a86104f990068adbd3cf2d275cd6` | `CONFLICT` |
| Log4j API | `org.apache.logging.log4j:log4j-api:2.25.2` | `CONFLICTING_LICENSE_EVIDENCE` | `01974cf46d6d6222f197a839970039c612c7dbd6d04073fff3cbc22d42c59b90` | `0956096a2502408c958a83174f2b6a57dcb2e5b07bb914c848732b44b8abbdc3` | `6923bd90cbbbbe4d7e5e99013097559ba6228b73` | `CONFLICT` |
| picocli | `info.picocli:picocli:4.7.7` | `CONFLICTING_LICENSE_EVIDENCE` | `87916611c616588b20d987868f96e622de6ed447e4b1ff5b662ebd947773e9a6` | `1b18d363134df66631d2b9f7475068d734225ba389cdf9082a1bd8bda90d57d3` | `5fcd4415a2cf834a12b4cb1e262a007beaa6b4af` | `CONFLICT` |
| Reactor Core | `io.projectreactor:reactor-core:3.7.9` | `CONFLICTING_LICENSE_EVIDENCE` | `423e361d938ae0ec94ef56d2103dcaee7dfb041399570b7403b1e2adf37555bd` | `3fce4a2502cd5a47fd3622ccdbd711b217a36d99b41c4c312923fedf8b31cd3b` | `4965f64483acdbd3cf0ba00764b35afbf9ff460c` | `CONFLICT` |

The acquisition receipts preserve the exact source URLs, archive/POM hashes,
source-tree hashes, correspondence entries, detached-signature bytes, request
and response hashes, and qualification decisions. The qualification set hash is
`fe7e32413d304243d8e7ead179f014ac90f88470233fc584165aadc272c723dc`.
The append-only disclosed registry manifest hash is
`7cbac3b9ce45b697aea4f8be77b7fff9804c395d43631e4676eb9fa71ac3d68a`.

Because only one distinct eligible root was available, there is no selected
final corpus. Callable-file, callable-target, type, package, overload,
constructor, generic-method, throws, nested-member, and source-share census
values are `NOT_MEASURED`.

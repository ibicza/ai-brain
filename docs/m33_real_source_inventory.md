# M-33 real source inventory

F12 is `ad3e35a36fcaafa267f3181b248c8269cb70287f`. The frozen selector
byte hash is `70b2143c475fb654d2ed4ff4c57cc9c6b3c5f02c922083f587ba3e63118d1bac`.
The final receipt manifest is
`28c08bfd5d33aa8185b52d8de0fe06f622dd6d34792d7ba763c277ca7efc7ab1`.

| Bundle | Identity/version | License | Documents | Words |
|---|---|---|---:|---:|
| kinematics | BCcampus College Physics one-dimensional kinematics, 2017-10-24 sitemap snapshot | CC BY 4.0 | 9 | 22,437 |
| biology | Concepts of Biology 1st Canadian Edition, Chapter 3 Cell Structure, 2021-03-04 sitemap snapshot | CC BY 4.0 | 6 | 13,231 |
| history | NPS Manzanar and US National Archives Japanese relocation materials, retrieved 2026-08-29 | US government public material | 2 | 3,528 |
| Java | OpenJDK JDK 21 GA `java.util`, tag commit `890adb6410dab4606a4f26a942aed02fb2f55387` | GPL-2.0 with Classpath Exception 2.0 | 8 | 55,087 |

Total: 25 immutable snapshots and 94,283 words. All snapshots are UTF-8 with
LF and contain no compiler annotations. The initial frozen downloader acquired
17 static snapshots and then received HTTP 403 from the sealed Library of
Congress URL. The two-source history minimum remains satisfied, but the missing
LOC snapshot is a black-box limitation. Static pages were reacquired through
the unchanged frozen adapter; their snapshot hashes were byte-identical. The
OpenJDK URLs timed out from the HTTP client and were acquired from the exact
frozen Git tag using a sparse clone, then passed through the frozen LF adapter.

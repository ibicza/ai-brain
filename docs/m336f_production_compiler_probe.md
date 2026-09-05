# M-33.6f production compiler probe

The production probe fixes the complete frozen Microsoft OpenJDK provider manifest, javac 21.0.11, release 21, UTF-8, `-proc:none`, locale-neutral `-XDrawDiagnostics`, canonical source order, an empty frozen classpath and isolated output. It removes ambient classpath/tool options and exposes no absolute path or localized message. Exact executable SHA selects and verifies the local provider platform without an unaudited version subprocess.

Semantic compiler identity is `3ccdf9ac1127058ae9152c913fa03f246b860227bee28e4ca69f4418358c231f` on both platforms. The Windows development qualification used executable hash `43ed8ede602fe115d7690463f98ad651abade9041b0bbe9f11825d8f0a499475` and platform probe hash `e44aee23d656861112ed90e1b5cb6fd3351a53c8d9b6ff24f4754409877ea680`. The executable/probe values are platform attestations and do not enter compiler-report, compilation-run, trust-decision or pack semantic identity.

The 180-file development production reported 34 diagnostics: 24 errors and 10 warnings. It had zero unknown scopes, zero unbound source units and zero malformed output rows; four diagnostics legitimately bind to zero declaration IDs and remain visible under their deterministic source-unit policy. Twelve callable declarations were withheld by compiler evidence. No trusted target retained a header-blocking, enclosing-type-blocking or other applicable compiler diagnostic.

The final development compiler report hash is `0584439664123ad3afc17d57b86e3dfb9273fcd2c2b1cbbd3a8638a514c7ef14`; production output hash is `7f731d776d01cdcf43c466f7b7b79919afa6d01345be55a846753ed62728ef6b`. These hashes are rehearsal evidence only and will be regenerated from clean exact R21.

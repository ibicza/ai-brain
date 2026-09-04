# Typed disclosure claims

Each protected role has explicit field paths and claim kinds. Claims bind role, artifact path, JSON field path, value, value hash, secrecy class, predeclared flag, and claim hash. Source bytes and observed archive/source/tree/selection/target/production/pack/oracle/golden/evaluation/decision identities are protected.

Coordinates, versions, SPDX, generic license filenames, the canonical standard-license hash, expected reports, role-manifest path, and selector-receipt path are not secrets. `NOT_AVAILABLE` is not a secret identity. Supplied claim sets must exactly equal derived claims; deletion, path changes, hash changes, or caller `PREDECLARED` markings fail. Neutral artifacts containing protected structured fields fail role validation.

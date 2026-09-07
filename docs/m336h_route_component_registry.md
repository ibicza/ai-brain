# M-33.6h route component registry

`M336HFinalJavaRouteRegistry` binds all 21 required route roles to importable callables. Each binding records the component ID and version, module and qualified callable, source hash, signature hash, request and response schema hashes, execution environments, confidentiality role, dependency IDs, and binding hash.

Registry validation imports and resolves each callable, recomputes its source and signature identities, verifies schema identities, rejects duplicates and unresolved string-only components, checks every dependency, detects cycles, and rejects private platform paths. `M336HFinalJavaRouteManifest` is derived from the validated registry rather than independently hand-written.

The selector route component is `m336h.final-compilation-closure-selector-route.v1`; its algorithm remains `m336f.compilation-closure-selector.v1`.

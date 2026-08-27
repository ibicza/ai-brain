# M-28 Chemistry CLI

Entry point: `ai-brain-chemistry`.

Commands: `build-domain`, `verify`, `list-elements`, `show-element`, `parse-formula`, `molar-mass`, `mass-to-moles`, `moles-to-mass`, `moles-to-entities`, `route-text`, `provenance`, `backup`, `restore`, and `export`.

Calculation commands return `PREPARED` unless `--confirm` is supplied. `route-text` never confirms automatically. The default pack root is `artifacts/domains/chemistry/m28`.

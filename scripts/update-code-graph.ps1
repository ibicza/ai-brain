$ErrorActionPreference = "Stop"

uvx --from code-review-graph code-review-graph build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

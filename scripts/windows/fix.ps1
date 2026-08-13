$ErrorActionPreference = "Stop"

Write-Host "Running ruff auto-fix..."
uv run ruff check . --fix

Write-Host "Running ruff formatter..."
uv run ruff format .

Write-Host "Done."
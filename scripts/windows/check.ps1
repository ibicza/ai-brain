$ErrorActionPreference = "Stop"

Write-Host "Checking ruff..."
uv run ruff check .

Write-Host "Checking format..."
uv run ruff format --check .

Write-Host "Running tests..."
uv run pytest -q

Write-Host "All checks passed."
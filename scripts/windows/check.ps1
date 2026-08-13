$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Title,

        [Parameter(Mandatory = $true)]
        [string] $Executable,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )

    Write-Host $Title
    & $Executable @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

Invoke-Checked "Checking ruff..." "uv" "run" "ruff" "check" "."
Invoke-Checked "Checking format..." "uv" "run" "ruff" "format" "--check" "."
Invoke-Checked "Running tests..." "uv" "run" "pytest" "-q"

Write-Host "All checks passed."
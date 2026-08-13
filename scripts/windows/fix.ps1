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

Invoke-Checked "Running ruff auto-fix..." "uv" "run" "ruff" "check" "." "--fix"
Invoke-Checked "Running ruff formatter..." "uv" "run" "ruff" "format" "."

Write-Host "Done."
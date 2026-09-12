param(
    [Parameter(Mandatory = $true)]
    [string]$InvocationPlan,

    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "execute")]
    [string]$Operation
)

$ErrorActionPreference = "Stop"
$planPath = (Resolve-Path -LiteralPath $InvocationPlan).Path
$plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json

$expectedFields = @(
    "bootstrap_script",
    "contract_role",
    "execute_arguments",
    "execute_startup_receipt",
    "expected_bootstrap_source_hash",
    "expected_environment_prefix",
    "expected_project_source_identity",
    "expected_python_executable_hash",
    "expected_python_implementation",
    "expected_python_version",
    "expected_target_source_hash",
    "git_executable",
    "invocation_plan_hash",
    "platform_role",
    "powershell_executable",
    "process_role",
    "python_executable",
    "repository",
    "sanitized_environment",
    "schema_version",
    "startup_policy",
    "target",
    "target_kind",
    "validate_arguments",
    "validate_startup_receipt",
    "working_directory"
) | Sort-Object
$actualFields = @($plan.PSObject.Properties.Name) | Sort-Object
if (
    (Compare-Object $expectedFields $actualFields) -or
    $plan.schema_version -ne 1 -or
    $plan.contract_role -ne "M336K5_PRIVATE_PYTHON_INVOCATION_PLAN" -or
    $plan.platform_role -ne "WINDOWS" -or
    -not [System.IO.Path]::IsPathRooted([string]$plan.python_executable) -or
    -not [System.IO.Path]::IsPathRooted([string]$plan.bootstrap_script) -or
    -not [System.IO.Path]::IsPathRooted([string]$plan.working_directory)
) {
    throw "M336K5 private invocation plan shape is invalid"
}

$python = (Resolve-Path -LiteralPath ([string]$plan.python_executable)).Path
$bootstrap = (Resolve-Path -LiteralPath ([string]$plan.bootstrap_script)).Path
$workingDirectory = (Resolve-Path -LiteralPath ([string]$plan.working_directory)).Path
$environment = @{}
foreach ($pair in $plan.sanitized_environment.variables) {
    if ($pair.Count -ne 2 -or $environment.ContainsKey([string]$pair[0])) {
        throw "M336K5 sanitized environment contains an invalid pair"
    }
    $environment[[string]$pair[0]] = [string]$pair[1]
}
foreach ($forbidden in @(
    "PYTHONBREAKPOINT",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE"
)) {
    if ($environment.ContainsKey($forbidden)) {
        throw "M336K5 sanitized environment retained a forbidden variable"
    }
}
if (
    $environment["PYTHONNOUSERSITE"] -ne "1" -or
    $environment["PYTHONDONTWRITEBYTECODE"] -ne "1" -or
    $environment["PYTHONHASHSEED"] -ne "0" -or
    $environment["PYTHONUTF8"] -ne "1" -or
    $environment["PIP_NO_INDEX"] -ne "1" -or
    $environment["UV_OFFLINE"] -ne "1" -or
    $environment["TZ"] -ne "UTC" -or
    $environment["PATH"] -ne ""
) {
    throw "M336K5 sanitized environment lost a required invariant"
}

$start = [System.Diagnostics.ProcessStartInfo]::new()
$start.FileName = $python
$start.WorkingDirectory = $workingDirectory
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.Environment.Clear()
foreach ($name in $environment.Keys) {
    $start.Environment[$name] = $environment[$name]
}
foreach ($argument in @(
    "-s",
    "-B",
    $bootstrap,
    "--invocation-plan",
    $planPath,
    "--operation",
    $Operation
)) {
    [void]$start.ArgumentList.Add([string]$argument)
}

$process = [System.Diagnostics.Process]::Start($start)
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()
if ($stdout.Length -gt 0) {
    [Console]::Out.Write($stdout)
}
if ($stderr.Length -gt 0) {
    [Console]::Error.Write($stderr)
}
exit $process.ExitCode

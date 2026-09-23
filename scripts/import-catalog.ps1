param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("eco-automacao", "portwell", "choice-tech")]
    [string]$Company
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
& ".\.venv\Scripts\python.exe" -m scripts.import_catalog --company $Company --commit


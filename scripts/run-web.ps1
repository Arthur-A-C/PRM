param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Arguments = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", $Port)
if ($Reload) { $Arguments += "--reload" }
& ".\.venv\Scripts\python.exe" @Arguments


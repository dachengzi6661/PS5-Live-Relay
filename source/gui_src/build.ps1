# Build launcher (ASCII only). Prefer build.py for reliable UTF-8 handling.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
    $py = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $py) {
    Write-Error "Python not found. Install Python 3.10+ and make sure it is on PATH."
    exit 1
}

& $py build.py
if ($LASTEXITCODE -ne 0) { Write-Error "Build failed"; exit 1 }

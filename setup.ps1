# Travel Agent - one-time environment setup
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$SpiderDir = Join-Path $Root "tools\xhs_tool\Spider_XHS"

Write-Host "==> Python dependencies"
pip install -r (Join-Path $Root "requirements.txt")

Write-Host ""
Write-Host "==> XHS Spider npm dependencies"
if (-not (Test-Path (Join-Path $SpiderDir "node_modules"))) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCmd) { throw "npm not found. Please install Node.js first." }
    & $npmCmd.Source install --prefix $SpiderDir
    Write-Host "npm install done."
} else {
    Write-Host "node_modules already exists, skipping."
}

Write-Host ""
Write-Host "Setup complete. You can now start the services."

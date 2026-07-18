# Hosts a local Archipelago server for testing the Drova client.
# Invoked by the Rider "Host AP Server" run configuration (via host_server.cmd).
#
# Resolves everything relative to this repo so it survives the repos tree being moved:
#   <repos>/ArchipelagoDrova/tools/host_server.ps1  ->  <repos>/Archipelago
# and hosts the newest seed in Archipelago/output on port 38281 (the mod's default).

param(
    [int]$Port = 38281
)

$ErrorActionPreference = 'Stop'

$reposRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # <repos>
$apDir = Join-Path $reposRoot 'Archipelago'
$server = Join-Path $apDir 'MultiServer.py'

if (-not (Test-Path $server)) {
    Write-Host "Archipelago checkout not found at $apDir." -ForegroundColor Red
    Write-Host "Expected MultiServer.py there. Clone Archipelago into that folder or fix the path." -ForegroundColor Red
    exit 1
}

$outputDir = Join-Path $apDir 'output'
$seed = Get-ChildItem -Path $outputDir -Filter '*.zip' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $seed) {
    Write-Host "No seed in $outputDir." -ForegroundColor Red
    Write-Host "Generate one first, e.g. from $apDir :" -ForegroundColor Yellow
    Write-Host "    python Generate.py" -ForegroundColor Yellow
    Write-Host "(a YAML with 'name: Drova' lives in Archipelago\Players so the slot matches the mod's config)." -ForegroundColor Yellow
    exit 1
}

Write-Host "Hosting $($seed.Name) on port $Port  (connect: localhost / $Port / slot Drova)" -ForegroundColor Green
Set-Location $apDir
# Archipelago's ModuleUpdate imports pkg_resources, which emits a harmless deprecation warning.
# Silence just that one line so the server console stays readable; everything else still prints.
$env:PYTHONWARNINGS = 'ignore:pkg_resources is deprecated as an API'
python MultiServer.py "$($seed.FullName)" --port $Port

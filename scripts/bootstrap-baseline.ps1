$ErrorActionPreference = "Stop"

Write-Host "[RIG] Building baseline graph..."
rig-build build --repo . --out .dist/rig.json

if (!(Test-Path .rig)) {
    New-Item -ItemType Directory -Path .rig | Out-Null
}

if (!(Test-Path .dist)) {
    New-Item -ItemType Directory -Path .dist | Out-Null
}

Copy-Item .dist/rig.json .rig/baseline-rig.json -Force
Copy-Item .dist/rig.json .rig/baseline.json -Force
Copy-Item .dist/rig.json .dist/baseline-rig.json -Force
Write-Host "[RIG] Baseline written to .rig/baseline-rig.json, .rig/baseline.json, and .dist/baseline-rig.json"

[CmdletBinding()]
param(
    [string]$OutputDirectory = "$PSScriptRoot\..\artifacts\windows-inventory"
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget export --output (Join-Path $OutputDirectory 'winget.json') --accept-source-agreements
}
if (Get-Command scoop -ErrorAction SilentlyContinue) {
    scoop export | Set-Content (Join-Path $OutputDirectory 'scoop.json')
}

Get-InstalledModule -ErrorAction SilentlyContinue |
    Select-Object Name, Version |
    ConvertTo-Json |
    Set-Content (Join-Path $OutputDirectory 'psgallery.json')

Write-Host "Inventory captured under $OutputDirectory. It is ignored until reviewed."

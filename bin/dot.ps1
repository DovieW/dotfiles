[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('bootstrap', 'apply', 'doctor', 'package', 'repos', 'secrets')]
    [string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ProfileName = 'windows-host'

for ($i = 0; $i -lt $Remaining.Count; $i++) {
    if ($Remaining[$i] -eq '--profile' -and ($i + 1) -lt $Remaining.Count) {
        $ProfileName = $Remaining[$i + 1]
    }
}

function Test-DotPrerequisites {
    $required = @('git', 'bw', 'gh', 'pwsh')
    $missing = @($required | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
    if ($missing.Count -gt 0) {
        Write-Error @"
Missing prerequisites: $($missing -join ', ')
Windows is inventory-only; install them manually:
  winget install Git.Git Bitwarden.CLI GitHub.cli Microsoft.PowerShell
"@
    }
}

function Install-DotLinks {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $profileTarget = Join-Path $documents 'PowerShell\Microsoft.PowerShell_profile.ps1'
    $profileSource = Join-Path $Root 'config\powershell\profile.ps1'
    New-Item -ItemType Directory -Force -Path (Split-Path $profileTarget) | Out-Null
    $stub = ". '$($profileSource.Replace("'", "''"))'"
    if (-not (Test-Path $profileTarget) -or (Get-Content $profileTarget -Raw) -ne $stub) {
        Set-Content -Path $profileTarget -Value $stub -NoNewline
    }
}

switch ($Command) {
    'bootstrap' {
        Test-DotPrerequisites
        Install-DotLinks
        Write-Host "Windows bootstrap checks passed for $ProfileName. Application manifests are record-only."
    }
    'apply' {
        Test-DotPrerequisites
        Install-DotLinks
        Write-Host "Applied Windows configuration. No applications were installed."
    }
    'doctor' {
        Test-DotPrerequisites
        Write-Host '[OK] Windows prerequisites'
        Write-Host '[OK] Windows application policy: inventory-only'
    }
    default {
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            throw "The '$Command' workflow currently requires Python. Install it manually or run from WSL."
        }
        & python (Join-Path $Root 'bin\dot') $Command @Remaining
        exit $LASTEXITCODE
    }
}

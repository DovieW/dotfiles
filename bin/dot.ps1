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
    $required = @('git', 'bw', 'gh', 'pwsh', 'python')
    $missing = @($required | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
    if ($missing.Count -gt 0) {
        Write-Error @"
Missing prerequisites: $($missing -join ', ')
Windows is inventory-only; install them manually:
  winget install Bitwarden.Bitwarden Bitwarden.CLI Git.Git GitHub.cli Google.Chrome Microsoft.PowerShell Python.Python.3.13
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
    $gitInclude = Join-Path $Root 'config\git\root.gitconfig'
    $includes = @(git config --global --get-all include.path 2>$null)
    if ($includes -notcontains $gitInclude) {
        git config --global --add include.path $gitInclude
    }
}

switch ($Command) {
    'bootstrap' {
        Test-DotPrerequisites
        Install-DotLinks
        gh auth status --hostname github.com 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            gh auth login --hostname github.com --web --git-protocol https --scopes 'admin:public_key,admin:ssh_signing_key'
        }
        Write-Host 'Chrome and Bitwarden are installed. Sign in to Bitwarden Desktop and enable its SSH agent.'
        Read-Host 'Press Enter to provision this device identity and repositories'
        & python (Join-Path $Root 'bin\dot') secrets sync --profile $ProfileName
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & python (Join-Path $Root 'bin\dot') repos sync --profile $ProfileName
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        Write-Host "Windows bootstrap completed for $ProfileName. Normal application management remains inventory-only."
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

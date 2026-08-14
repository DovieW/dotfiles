$ErrorActionPreference = 'Stop'
$Media = Split-Path -Parent $MyInvocation.MyCommand.Path

Get-Content (Join-Path $Media 'SHA256SUMS') | ForEach-Object {
    if ($_ -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Invalid SHA256SUMS line: $_" }
    $Expected = $Matches[1]
    $Relative = $Matches[2]
    $Actual = (Get-FileHash -Algorithm SHA256 (Join-Path $Media $Relative)).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) { throw "Checksum mismatch: $Relative" }
}

$Packages = @(
    'Bitwarden.Bitwarden', 'Bitwarden.CLI', 'Git.Git', 'GitHub.cli',
    'Google.Chrome', 'Microsoft.PowerShell', 'Python.Python.3.13'
)
foreach ($Package in $Packages) {
    winget install --id $Package --exact --silent --accept-package-agreements --accept-source-agreements
}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
    [Environment]::GetEnvironmentVariable('Path', 'User')

$Destination = Join-Path $HOME 'repos\dotfiles'
if (Test-Path $Destination) {
    if (-not (Test-Path (Join-Path $Destination '.git'))) {
        throw "$Destination exists and is not a Git checkout; it was not changed."
    }
    if ((git -C $Destination status --porcelain)) {
        throw "$Destination has local changes; it was not changed."
    }
    $Origin = git -C $Destination remote get-url origin
    if ($Origin -notin @('git@github.com:DovieW/dotfiles.git', 'https://github.com/DovieW/dotfiles.git')) {
        throw "$Destination has an unexpected origin; it was not changed."
    }
    git -C $Destination fetch (Join-Path $Media 'payload\dotfiles.bundle') master
    git -C $Destination merge --ff-only FETCH_HEAD
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    git clone (Join-Path $Media 'payload\dotfiles.bundle') $Destination
    git -C $Destination remote remove origin 2>$null
    git -C $Destination remote add origin git@github.com:DovieW/dotfiles.git
}

& (Join-Path $Destination 'bin\dot.ps1') bootstrap --profile windows-host
if ($LASTEXITCODE) { exit $LASTEXITCODE }

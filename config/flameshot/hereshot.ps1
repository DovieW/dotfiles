param(
    [string]$Filename
)

$ErrorActionPreference = 'Stop'

if (-not $Filename) {
    $Filename = "screenshot-{0}.png" -f (Get-Date -Format "yyyyMMdd-HHmmss")
}

function Get-FlameshotPath {
    $cmd = Get-Command flameshot.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $cmd = Get-Command flameshot-cli.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\Flameshot\bin\flameshot.exe",
        "$env:ProgramFiles\Flameshot\bin\flameshot-cli.exe",
        "$env:LocalAppData\Programs\Flameshot\bin\flameshot.exe",
        "$env:LocalAppData\Programs\Flameshot\bin\flameshot-cli.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Could not find Flameshot."
}

$flameshot = Get-FlameshotPath
$outFile = Join-Path (Get-Location) $Filename

& $flameshot gui --path $outFile

if (Test-Path $outFile) {
    $outFile
} else {
    Write-Error "No file was written. You may have cancelled the capture."
}

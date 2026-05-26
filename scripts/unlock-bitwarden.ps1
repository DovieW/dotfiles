[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Test-Command {
	param([Parameter(Mandatory)][string]$Name)
	return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command bw)) {
	throw 'Bitwarden CLI (bw) is not installed. Run setup.ps1 -WithBitwarden first.'
}

$statusJson = bw status 2>$null
$status = $null
if ($statusJson) {
	$status = $statusJson | ConvertFrom-Json
}

if (-not $status -or $status.status -eq 'unauthenticated') {
	bw login | Out-Host
}

$session = bw unlock --raw
if ([string]::IsNullOrWhiteSpace($session)) {
	throw 'Bitwarden unlock did not return a session token.'
}

$env:BW_SESSION = $session
Write-Host 'BW_SESSION is set for this PowerShell session.' -ForegroundColor Green

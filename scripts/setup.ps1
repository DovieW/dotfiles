[CmdletBinding()]
param(
	[switch]$WindowsCore,
	[switch]$DotfilesOnly,
	[switch]$AllSafe,
	[switch]$WithBitwarden,
	[switch]$WithPrivate,
	[switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

function Write-Section {
	param([Parameter(Mandatory)][string]$Text)
	Write-Host "`n== $Text ==" -ForegroundColor Cyan
}

function Test-Command {
	param([Parameter(Mandatory)][string]$Name)
	return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Invoke-Step {
	param(
		[Parameter(Mandatory)][string]$Description,
		[Parameter(Mandatory)][scriptblock]$Script
	)
	Write-Host "+ $Description" -ForegroundColor DarkCyan
	if (-not $DryRun) {
		& $Script
	}
}

function Confirm-Step {
	param([Parameter(Mandatory)][string]$Prompt)

	if (Test-Command gum) {
		gum confirm $Prompt
		return ($LASTEXITCODE -eq 0)
	}

	$response = Read-Host "$Prompt [y/N]"
	return $response -match '^(y|yes)$'
}

function Ensure-WingetPackage {
	param(
		[Parameter(Mandatory)][string]$CommandName,
		[Parameter(Mandatory)][string]$PackageId
	)

	if (Test-Command $CommandName) {
		return
	}

	if (-not (Test-Command winget)) {
		Write-Warning "winget not found; install $PackageId manually."
		return
	}

	Invoke-Step "Install $PackageId" {
		winget install --id $PackageId -e --accept-source-agreements --accept-package-agreements
	}
}

function Ensure-PowerShellModule {
	param([Parameter(Mandatory)][string]$Name)
	if (Get-Module -ListAvailable -Name $Name) {
		return
	}
	Invoke-Step "Install PowerShell module $Name" {
		Install-Module -Name $Name -Scope CurrentUser -Force -AllowClobber
	}
}

function Apply-Dotfiles {
	Ensure-WingetPackage -CommandName chezmoi -PackageId 'twpayne.chezmoi'
	if (-not (Test-Command chezmoi)) {
		throw 'chezmoi is not available.'
	}
	Invoke-Step 'Apply chezmoi dotfiles' {
		chezmoi apply --source $RepoRoot
	}
}

function Install-WindowsTools {
	Ensure-WingetPackage -CommandName git -PackageId 'Git.Git'
	Ensure-WingetPackage -CommandName gh -PackageId 'GitHub.cli'
	Ensure-WingetPackage -CommandName oh-my-posh -PackageId 'JanDeDobbeleer.OhMyPosh'
	Ensure-WingetPackage -CommandName zoxide -PackageId 'ajeetdsouza.zoxide'
	Ensure-WingetPackage -CommandName fzf -PackageId 'junegunn.fzf'
	Ensure-WingetPackage -CommandName rg -PackageId 'BurntSushi.ripgrep.MSVC'
	Ensure-WingetPackage -CommandName jq -PackageId 'jqlang.jq'
}

function Install-PowerShellProfile {
	Ensure-PowerShellModule -Name 'PSReadLine'
	Ensure-PowerShellModule -Name 'posh-git'
	Ensure-PowerShellModule -Name 'Terminal-Icons'
	Ensure-PowerShellModule -Name 'PSFzf'

	$profilePath = Join-Path $HOME '.config\powershell\profile.ps1'
	$stub = @"
`$profilePath = Join-Path `$HOME '.config\powershell\profile.ps1'
if (Test-Path -LiteralPath `$profilePath) {
	. `$profilePath
}
"@

	foreach ($target in @($PROFILE.CurrentUserCurrentHost, $PROFILE.CurrentUserAllHosts)) {
		$parent = Split-Path -Parent $target
		Invoke-Step "Ensure profile directory $parent" {
			New-Item -ItemType Directory -Path $parent -Force | Out-Null
		}
		Invoke-Step "Write PowerShell profile stub $target" {
			Set-Content -LiteralPath $target -Value $stub -Encoding UTF8
		}
	}
}

function Ensure-Bitwarden {
	if (-not (Test-Command bw)) {
		Ensure-WingetPackage -CommandName bw -PackageId 'Bitwarden.CLI'
	}
	if (-not (Test-Command bw)) {
		throw 'Bitwarden CLI (bw) is not available.'
	}
}

function Run-WindowsCore {
	Install-WindowsTools
	Apply-Dotfiles
	Install-PowerShellProfile
}

Write-Section 'Dovie dotfiles setup'

if ($WindowsCore -or $AllSafe) {
	Run-WindowsCore
} elseif ($DotfilesOnly) {
	Apply-Dotfiles
} else {
	if (Confirm-Step 'Install/update common Windows CLI tools?') {
		Install-WindowsTools
	}
	if (Confirm-Step 'Apply chezmoi dotfiles?') {
		Apply-Dotfiles
	}
	if (Confirm-Step 'Install PowerShell modules and profile stubs?') {
		Install-PowerShellProfile
	}
}

if ($WithBitwarden) {
	Ensure-Bitwarden
	Write-Host 'Run scripts/unlock-bitwarden.ps1 to set BW_SESSION for this PowerShell session.' -ForegroundColor Yellow
}

if ($WithPrivate) {
	if (-not (Test-Command gh)) {
		Ensure-WingetPackage -CommandName gh -PackageId 'GitHub.cli'
	}
	Write-Host 'Private setup uses the existing DovieW/files repo as the workbench/archive.' -ForegroundColor Yellow
	Write-Host 'Clone it manually where desired: gh repo clone DovieW/files ~/repos/files' -ForegroundColor Yellow
}

Write-Section 'Done'

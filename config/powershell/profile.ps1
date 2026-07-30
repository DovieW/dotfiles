# Dovie's PowerShell 7 profile
# Source-controlled from: ~/repos/dotfiles/config/powershell/
# Loaded by a tiny stub placed at $PROFILE by setup.ps1

# Keep profile resilient: if a tool/module isn't installed yet, nothing should crash.

function Test-Command {
	param(
		[Parameter(Mandatory)]
		[string]$Name
	)
	return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

# Startup tuning:
# Some PowerShell modules are surprisingly expensive to import on Windows.
# If you want a faster shell start, set:
#   $env:DOVIE_PWSH_FASTSTART = '1'
# (You can set it persistently via the User environment variables.)
$script:DovieFastStart = ($env:DOVIE_PWSH_FASTSTART -eq '1')

# -----------------------------
# Editor defaults (EDITOR/VISUAL)
# -----------------------------
if (-not $env:EDITOR -or [string]::IsNullOrWhiteSpace($env:EDITOR)) {
	if (Test-Command code) {
		$env:EDITOR = 'code'
		$env:VISUAL = 'code'
	} elseif (Test-Command nvim) {
		$env:EDITOR = 'nvim'
		$env:VISUAL = 'nvim'
	} else {
		$env:EDITOR = 'notepad'
		$env:VISUAL = 'notepad'
	}
}

# -----------------------------
# PSReadLine (modern line editing)
# -----------------------------
if (Get-Module -ListAvailable -Name PSReadLine) {
	Import-Module PSReadLine -ErrorAction SilentlyContinue

	# History + prediction (fish-ish)
	try {
		Set-PSReadLineOption -BellStyle None
		Set-PSReadLineOption -HistoryNoDuplicates
		Set-PSReadLineOption -HistorySearchCursorMovesToEnd
		if ($script:DovieFastStart) {
			Set-PSReadLineOption -PredictionSource History
		} else {
			Set-PSReadLineOption -PredictionSource HistoryAndPlugin
		}
		Set-PSReadLineOption -PredictionViewStyle ListView
		Set-PSReadLineOption -EditMode Windows

		# Tab cycles completion (more bash-like)
		Set-PSReadLineKeyHandler -Key Tab -Function MenuComplete

		# Bash-ish shortcuts
		# Ctrl+P / Ctrl+N: previous/next history item
		Set-PSReadLineKeyHandler -Key Ctrl+p -Function PreviousHistory
		Set-PSReadLineKeyHandler -Key Ctrl+n -Function NextHistory
		# Ctrl+U: kill from cursor back to start of line
		Set-PSReadLineKeyHandler -Key Ctrl+u -Function BackwardKillLine

		# Ctrl+r reverse search (zsh muscle memory)
		if (Get-Command -Name Set-PSReadLineKeyHandler -ErrorAction SilentlyContinue) {
			Set-PSReadLineKeyHandler -Key Ctrl+r -Function ReverseSearchHistory
		}
	} catch {
		# If PSReadLine changes across versions, keep the shell usable.
	}
}

# -----------------------------
# Pretty icons in directory listings
# -----------------------------
if (-not $script:DovieFastStart) {
	Import-Module Terminal-Icons -ErrorAction SilentlyContinue
}

# -----------------------------
# Git completions
# -----------------------------
if (-not $script:DovieFastStart) {
	Import-Module posh-git -ErrorAction SilentlyContinue
}

# -----------------------------
# Prompt: Oh My Posh (if installed)
# -----------------------------
if (Test-Command 'oh-my-posh') {
	$ompConfig = Join-Path $PSScriptRoot 'dovie.omp.json'
	try {
		if (Test-Path -LiteralPath $ompConfig) {
			oh-my-posh init pwsh --config $ompConfig | Invoke-Expression
		} else {
			oh-my-posh init pwsh | Invoke-Expression
		}
	} catch {
		# Ignore prompt init failures.
	}
}

# -----------------------------
# zoxide (smart cd)
# -----------------------------
if (Test-Command zoxide) {
	try {
		# zoxide outputs a script; Out-String makes it safe for Invoke-Expression
		Invoke-Expression (& { zoxide init powershell | Out-String })
	} catch {
	}
}

# -----------------------------
# fzf integration (Ctrl+t files, Ctrl+r history)
# -----------------------------
if (-not $script:DovieFastStart) {
	if ((Get-Module -ListAvailable -Name PSFzf) -and (Test-Command fzf)) {
		Import-Module PSFzf -ErrorAction SilentlyContinue
		if (Get-Command -Name Set-PsFzfOption -ErrorAction SilentlyContinue) {
			try {
				Set-PsFzfOption -PSReadlineChordProvider 'Ctrl+t' -PSReadlineChordReverseHistory 'Ctrl+r'
			} catch {
			}
		}
		if (Get-Command -Name Enable-PsFzfTabCompletion -ErrorAction SilentlyContinue) {
			try {
				Enable-PsFzfTabCompletion
			} catch {
			}
		}
	}
}

function Enable-DovieFullProfile {
	<#
	Loads the slower (but nice) extras if you started in fast mode.
	This is intentionally manual so startup can be quick.
	#>
	Import-Module Terminal-Icons -ErrorAction SilentlyContinue
	Import-Module posh-git -ErrorAction SilentlyContinue
	if ((Get-Module -ListAvailable -Name PSFzf) -and (Test-Command fzf)) {
		Import-Module PSFzf -ErrorAction SilentlyContinue
		try { Set-PsFzfOption -PSReadlineChordProvider 'Ctrl+t' -PSReadlineChordReverseHistory 'Ctrl+r' } catch { }
		try { Enable-PsFzfTabCompletion } catch { }
	}
}

# -----------------------------
# Bash/zsh-ish helper functions
# -----------------------------
function which {
	param([Parameter(Mandatory)][string]$Name)
	$cmd = Get-Command -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1
	if (-not $cmd) { return $null }

	# Prefer a real path when it's an external command.
	if ($cmd.Path) { return $cmd.Path }

	# For functions/aliases, show what it maps to.
	if ($cmd.Definition) { return $cmd.Definition }

	return $cmd.Source
}

function touch {
	param([Parameter(ValueFromRemainingArguments)][string[]]$Path)
	foreach ($p in $Path) {
		if ([string]::IsNullOrWhiteSpace($p)) { continue }
		if (Test-Path -LiteralPath $p) {
			try {
				(Get-Item -LiteralPath $p).LastWriteTime = Get-Date
			} catch {
			}
		} else {
			try {
				New-Item -ItemType File -Path $p -Force | Out-Null
			} catch {
			}
		}
	}
}

function .. { Set-Location .. }
function ... { Set-Location ../.. }
function .... { Set-Location ../../.. }

function mkcd {
	param([Parameter(Mandatory)][string]$Path)
	New-Item -ItemType Directory -Path $Path -Force | Out-Null
	Set-Location -LiteralPath $Path
}

function open {
	param([Parameter(Mandatory)][string]$Path)
	try {
		Start-Process -FilePath $Path | Out-Null
	} catch {
		try { Invoke-Item -LiteralPath $Path } catch { }
	}
}

function cproj {
	# Open current folder in VS Code if available
	if (Test-Command code) { code .; return }
	Write-Host 'VS Code (code) not found on PATH.'
}

function cclip {
	param([Parameter(Position = 0)][string[]]$Path)
	if ($Path.Count -gt 0) {
		Get-Content -LiteralPath $Path -Raw | clip.exe
		return
	}
	$input | clip.exe
}

function reload-profile {
	. $PROFILE
}

# Better ls variants if eza exists
function ll {
	if (Test-Command eza) { eza -lah --git; return }
	Get-ChildItem -Force | Format-Table
}

function la {
	if (Test-Command eza) { eza -la --git; return }
	Get-ChildItem -Force
}

function grep {
	param([Parameter(ValueFromRemainingArguments)][string[]]$Args)
	if (Test-Command rg) { rg @Args; return }
	Write-Host 'ripgrep (rg) not found; use Select-String instead.'
}

# Small convenience aliases (safe ones)
Set-Alias -Name g -Value git -ErrorAction SilentlyContinue

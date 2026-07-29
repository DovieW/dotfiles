$Root = Split-Path -Parent $PSScriptRoot

Describe 'Windows adapter' {
    It 'exists and parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $Root 'bin\dot.ps1'),
            [ref]$null,
            [ref]$errors
        ) | Out-Null
        $errors.Count | Should -Be 0
    }

    It 'documents inventory-only behavior' {
        Get-Content (Join-Path $Root 'profiles\windows-host.yml') -Raw |
            Should -Match '"windows_inventory_only": true'
    }
}

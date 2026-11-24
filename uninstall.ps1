# Ach! Uninstaller for Windows (PowerShell)
param(
    [string]$Prefix = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME ".local\share" }
$InstallBase = Join-Path $LocalAppData "ach"
$LegacyBase = Join-Path $LocalAppData "sessionlist"
$BinDir = Join-Path $InstallBase "bin"
$ConfigDir = Join-Path $HOME ".gemini\antigravity-cli\plugin_data\sessionlist"
$ConfigFile = Join-Path $ConfigDir "config.json"

function Remove-LauncherSet {
    param([string]$CmdName)
    if ([string]::IsNullOrWhiteSpace($CmdName)) { return }
    if ($CmdName -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$') { return }
    foreach ($suffix in @("", "-h", "-m")) {
        $Target = Join-Path $BinDir "${CmdName}${suffix}.cmd"
        if (Test-Path $Target) {
            Remove-Item -Force $Target -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Uninstalling Ach!..."

# 1. Remove cloned code (both current and legacy)
foreach ($dir in @($InstallBase, $LegacyBase)) {
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    }
}

# 2. Read custom alias from config if present
if (Test-Path $ConfigFile) {
    try {
        $Cfg = Get-Content -Path $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Cfg -and $Cfg.PSObject.Properties["cli_command"] -and $Cfg.cli_command) {
            Remove-LauncherSet -CmdName $Cfg.cli_command
        }
    } catch {
        # Non-fatal
    }
}

# 3. Remove standard generated aliases in ~/.local/bin/
foreach ($std in @("ach", "antig", "ag")) {
    Remove-LauncherSet -CmdName $std
}

# Also remove any custom prefix passed as argument
if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
    Remove-LauncherSet -CmdName $Prefix.Trim()
}

# 4. Remove config directory
if (Test-Path $ConfigDir) {
    Remove-Item -Recurse -Force $ConfigDir -ErrorAction SilentlyContinue
}

Write-Host "[OK] Successfully uninstalled Ach! from your system."

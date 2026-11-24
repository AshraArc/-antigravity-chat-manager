# Ach! Local Installer for Windows (PowerShell)
param(
    [string]$Prefix = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME ".local\share" }
$InstallDir = Join-Path $LocalAppData "ach\bin"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "ach.py"
$ConfigDir = Join-Path $HOME ".gemini\antigravity-cli\plugin_data\sessionlist"
$ConfigFile = Join-Path $ConfigDir "config.json"

function Resolve-Python3 {
    foreach ($candidate in @(
        @{ Exe = "py"; Args = "-3" },
        @{ Exe = "python3"; Args = "" },
        @{ Exe = "python"; Args = "" }
    )) {
        $cmd = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $ver = if ($candidate.Args) {
                    & $candidate.Exe $candidate.Args -c "import sys; print(sys.version_info[0])" 2>$null
                } else {
                    & $candidate.Exe -c "import sys; print(sys.version_info[0])" 2>$null
                }
                if ($ver -and $ver.Trim() -eq "3") {
                    return $candidate
                }
            } catch {
                continue
            }
        }
    }
    return $null
}

$Py = Resolve-Python3
if (-not $Py) {
    Write-Error "Error: Python 3 is required but was not found in PATH."
    exit 1
}
$PyCmd = if ($Py.Args) { "$($Py.Exe) $($Py.Args)" } else { $Py.Exe }

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Write-Host "=================================================="
Write-Host "                Ach! Installer                "
Write-Host "=================================================="

$DefaultCmd = "ach"
if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
    $CmdName = $Prefix.Trim()
} elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
    $UserCmd = Read-Host "Enter preferred alias/command prefix [default: $DefaultCmd]"
    $CmdName = if ([string]::IsNullOrWhiteSpace($UserCmd)) { $DefaultCmd } else { $UserCmd.Trim() }
} else {
    $CmdName = $DefaultCmd
}

if ($CmdName -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$') {
    Write-Error "Error: Invalid command prefix '$CmdName'. Use only letters, digits, '-' or '_'."
    exit 1
}

# 1. Quick list launcher: <cmd>-h.cmd
$BinH = Join-Path $InstallDir "${CmdName}-h.cmd"
@"
@echo off
if "%~1"=="" (
    $PyCmd "$ScriptPath" --list
) else (
    $PyCmd "$ScriptPath" %*
)
"@ | Set-Content -Path $BinH -Encoding ASCII

# 2. Interactive menu launcher: <cmd>-m.cmd
$BinM = Join-Path $InstallDir "${CmdName}-m.cmd"
@"
@echo off
$PyCmd "$ScriptPath" %*
"@ | Set-Content -Path $BinM -Encoding ASCII

# 3. Direct base shortcut: <cmd>.cmd
$BinBase = Join-Path $InstallDir "${CmdName}.cmd"
@"
@echo off
$PyCmd "$ScriptPath" %*
"@ | Set-Content -Path $BinBase -Encoding ASCII

# 4. Save chosen prefix to config file
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
try {
    $Cfg = @{}
    if (Test-Path $ConfigFile) {
        $Raw = Get-Content -Path $ConfigFile -Raw -Encoding UTF8
        if ($Raw) {
            $Parsed = $Raw | ConvertFrom-Json
            foreach ($prop in $Parsed.PSObject.Properties) {
                $Cfg[$prop.Name] = $prop.Value
            }
        }
    }
    $Cfg["cli_command"] = $CmdName
    $Cfg | ConvertTo-Json -Depth 4 | Set-Content -Path $ConfigFile -Encoding UTF8
} catch {
    # Non-fatal
}

# 5. Auto-register skills in Antigravity skill directories if they exist
$SkillSrc = Join-Path $ScriptDir "skills\ach"
if (Test-Path $SkillSrc) {
    $TargetSkillDirs = @(
        (Join-Path $HOME ".gemini\antigravity-cli\skills"),
        (Join-Path $HOME ".agents\skills")
    )
    foreach ($TargetDir in $TargetSkillDirs) {
        if (Test-Path $TargetDir) {
            $LegacySkill = Join-Path $TargetDir "sessionlist"
            if (Test-Path $LegacySkill) {
                Remove-Item -Recurse -Force $LegacySkill -ErrorAction SilentlyContinue
            }
            $Dest = Join-Path $TargetDir "ach"
            if (Test-Path $Dest) {
                Remove-Item -Recurse -Force $Dest -ErrorAction SilentlyContinue
            }
            Copy-Item -Recurse -Force $SkillSrc $Dest
            Write-Host "[OK] Registered skill in $Dest"
        }
    }
}

# 6. Ensure InstallDir is in User PATH
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathEntries = if ($UserPath) { $UserPath -split ";" | Where-Object { $_ } } else { @() }
$NormBin = $InstallDir.TrimEnd("\").ToLowerInvariant()
$AlreadyInPath = $false
foreach ($entry in $PathEntries) {
    if ($entry.TrimEnd("\").ToLowerInvariant() -eq $NormBin) {
        $AlreadyInPath = $true
        break
    }
}
if (-not $AlreadyInPath) {
    $NewUserPath = if ($UserPath) { "$UserPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    if ($env:PATH -notlike "*$InstallDir*") {
        $env:PATH = "$env:PATH;$InstallDir"
    }
    Write-Host "[OK] Added $InstallDir to your User PATH (restart your terminal if commands are not immediately found)."
}

Write-Host ""
Write-Host "[OK] Created executable launchers in ${InstallDir}:"
Write-Host "   - ${CmdName}-h.cmd (Quick table dump)"
Write-Host "   - ${CmdName}-m.cmd (Interactive manager)"
Write-Host "   - ${CmdName}.cmd   (Direct shortcut)"
Write-Host "=================================================="
Write-Host "  [OK] Ach! installation complete."
Write-Host "=================================================="
Write-Host "  1. In Terminal (Outside Chat):"
Write-Host "     Run:  ${CmdName}-h  (quick list)"
Write-Host "     Run:  ${CmdName}-m  (interactive menu)"
Write-Host ""
Write-Host "  2. In Antigravity (Inside Chat):"
Write-Host "     Commands: /find, /recall, /history, /sessions"
Write-Host "     Install plugin: agy plugin install `"$ScriptDir`""
Write-Host "     Ask agent: 'show my chat history' or search with '/find <topic>'"
Write-Host "=================================================="

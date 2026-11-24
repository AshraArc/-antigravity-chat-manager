# Ach! 1-Line Remote Installer for Windows (PowerShell)
param(
    [string]$Prefix = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PrimaryRepo = "https://github.com/AshraArc/ach-cli.git"
$FallbackRepo = "https://github.com/AshraArc/-antigravity-chat-manager.git"
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME ".local\share" }
$InstallBase = Join-Path $LocalAppData "ach"
$BinDir = Join-Path $InstallBase "bin"
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

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Error: 'git' is required but not installed."
    exit 1
}

$Py = Resolve-Python3
if (-not $Py) {
    Write-Error "Error: Python 3 is required but was not found in PATH."
    exit 1
}
$PyCmd = if ($Py.Args) { "$($Py.Exe) $($Py.Args)" } else { $Py.Exe }

if (Test-Path (Join-Path $InstallBase ".git")) {
    Write-Host "Updating existing Ach!..."
    try {
        git -C $InstallBase pull --quiet
    } catch {
        Write-Host "Pull failed, attempting remote update..."
        git -C $InstallBase remote set-url origin $PrimaryRepo 2>$null
        git -C $InstallBase pull --quiet 2>$null
    }
} else {
    Write-Host "Downloading Ach!..."
    if (Test-Path $InstallBase) {
        Remove-Item -Recurse -Force $InstallBase
    }
    try {
        git clone --depth 1 --quiet $PrimaryRepo $InstallBase 2>$null
    } catch {
        Write-Host "Primary repo failed, falling back to backup repository URL..."
        git clone --depth 1 --quiet $FallbackRepo $InstallBase
    }
}

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$DefaultPrefix = "ach"
if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
    $CmdPrefix = $Prefix.Trim()
} elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
    $UserCmd = Read-Host "Enter preferred alias/command prefix [default: $DefaultPrefix]"
    $CmdPrefix = if ([string]::IsNullOrWhiteSpace($UserCmd)) { $DefaultPrefix } else { $UserCmd.Trim() }
} else {
    $CmdPrefix = $DefaultPrefix
}

if ($CmdPrefix -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$') {
    Write-Error "Error: Invalid command prefix '$CmdPrefix'. Use only letters, digits, '-' or '_'."
    exit 1
}

$ScriptPath = Join-Path $InstallBase "ach.py"

# 1. Quick list launcher: <cmd>-h.cmd
$BinH = Join-Path $BinDir "${CmdPrefix}-h.cmd"
@"
@echo off
if "%~1"=="" (
    $PyCmd "$ScriptPath" --list
) else (
    $PyCmd "$ScriptPath" %*
)
"@ | Set-Content -Path $BinH -Encoding ASCII

# 2. Interactive menu launcher: <cmd>-m.cmd
$BinM = Join-Path $BinDir "${CmdPrefix}-m.cmd"
@"
@echo off
$PyCmd "$ScriptPath" %*
"@ | Set-Content -Path $BinM -Encoding ASCII

# 3. Direct base command: <cmd>.cmd
$BinBase = Join-Path $BinDir "${CmdPrefix}.cmd"
@"
@echo off
$PyCmd "$ScriptPath" %*
"@ | Set-Content -Path $BinBase -Encoding ASCII

# 4. Save chosen prefix to config.json
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
    $Cfg["cli_command"] = $CmdPrefix
    $Cfg | ConvertTo-Json -Depth 4 | Set-Content -Path $ConfigFile -Encoding UTF8
} catch {
    # Non-fatal
}

# 5. Clean up legacy / stale aliases if CmdPrefix changed
foreach ($legacy in @("antig", "ag")) {
    if ($CmdPrefix -ne $legacy) {
        foreach ($suffix in @("", "-h", "-m")) {
            $LegacyFile = Join-Path $BinDir "${legacy}${suffix}.cmd"
            if (Test-Path $LegacyFile) {
                Remove-Item -Force $LegacyFile -ErrorAction SilentlyContinue
            }
        }
    }
}

# 6. Clean up old temporary files and python caches in install base
if (Test-Path $InstallBase) {
    Get-ChildItem -Path $InstallBase -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $InstallBase -File -Recurse -Filter "*.tmp" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

# 7. Auto-register skills in Antigravity skill directories if they exist
$SkillSrc = Join-Path $InstallBase "skills\ach"
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

# 8. Ensure BinDir is in User PATH
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathEntries = if ($UserPath) { $UserPath -split ";" | Where-Object { $_ } } else { @() }
$NormBin = $BinDir.TrimEnd("\").ToLowerInvariant()
$AlreadyInPath = $false
foreach ($entry in $PathEntries) {
    if ($entry.TrimEnd("\").ToLowerInvariant() -eq $NormBin) {
        $AlreadyInPath = $true
        break
    }
}
if (-not $AlreadyInPath) {
    $NewUserPath = if ($UserPath) { "$UserPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    if ($env:PATH -notlike "*$BinDir*") {
        $env:PATH = "$env:PATH;$BinDir"
    }
    Write-Host "[OK] Added $BinDir to your User PATH (restart your terminal if commands are not immediately found)."
}

Write-Host "[OK] Installed ${CmdPrefix}, ${CmdPrefix}-h, ${CmdPrefix}-m to $BinDir"

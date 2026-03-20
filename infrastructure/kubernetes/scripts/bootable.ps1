#Requires -Version 5.1
<#
.SYNOPSIS
    Create a K3s worker node disk image (Windows wrapper for bootable.sh via WSL2).

.DESCRIPTION
    Handles all interactive prompts natively in PowerShell, manages WiFi config
    persistence (wifi.yaml), then delegates the actual disk image build to
    bootable.sh running inside a WSL2 Debian/Ubuntu distro.

.PARAMETER NodeName
    Optional label for the image filename (default: k3s-node).
    Hostname is derived from MAC address at first boot.

.PARAMETER Target
    WSL device path to write to (e.g. /dev/sdb). Ignored if -ImageOnly is set.

.PARAMETER ImageOnly
    Create a .img file without writing to a device.

.PARAMETER RebuildCache
    Force rebuild of cached rootfs tarballs inside WSL.

.EXAMPLE
    .\bootable.ps1 -ImageOnly
    .\bootable.ps1 -ImageOnly -RebuildCache
    .\bootable.ps1 my-batch -ImageOnly
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$NodeName = 'k3s-node',

    [Parameter(Position = 1)]
    [string]$Target,

    [switch]$ImageOnly,

    [switch]$RebuildCache
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ────────────────────────────────────────────────────────────────────

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = (Resolve-Path "$ScriptDir\..\..").Path
$ConfigDir   = Join-Path $RepoRoot 'kubernetes\config'
$WifiYaml    = Join-Path $ConfigDir 'wifi.yaml'

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Log   { param([string]$Msg) Write-Host "[OK]    $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }
function Write-Info  { param([string]$Msg) Write-Host "[INFO]  $Msg" -ForegroundColor Cyan }
function Write-Err   { param([string]$Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red }
function Write-Section { param([string]$Msg) Write-Host "`n--- $Msg ---`n" -ForegroundColor White }

# ── Ensure powershell-yaml module ────────────────────────────────────────────

if (-not (Get-Module -ListAvailable -Name 'powershell-yaml')) {
    Write-Info "Installing powershell-yaml module..."
    Install-Module -Name powershell-yaml -Scope CurrentUser -Force -AllowClobber
}
Import-Module powershell-yaml -ErrorAction Stop

# ── Check WSL2 ───────────────────────────────────────────────────────────────

Write-Section "Checking prerequisites"

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    Write-Err "WSL is not installed. Install WSL2:"
    Write-Host "  wsl --install"
    exit 1
}

# Find a Debian or Ubuntu WSL2 distro
# Note: wsl --list outputs UTF-16LE with null bytes — strip them before matching
$distros = (wsl --list --verbose 2>&1) -replace [char]0, '' |
    Where-Object { $_ -match '\s+2\s*$' } |
    ForEach-Object {
        if ($_ -match '^\s*\*?\s*(\S+)') { $Matches[1] }
    } |
    Where-Object { $_ -match '(?i)debian|ubuntu' }

if (-not $distros) {
    Write-Err "No Debian/Ubuntu WSL2 distro found."
    Write-Host "  Install one: wsl --install -d Debian"
    exit 1
}

$WslDistro = if ($distros -is [array]) { $distros[0] } else { $distros }
Write-Log "Using WSL2 distro: $WslDistro"

# Verify required tools inside WSL
$requiredTools = @('debootstrap', 'parted', 'mkfs.ext4', 'mkfs.vfat')
$missing = @()
foreach ($tool in $requiredTools) {
    $check = wsl -d $WslDistro -- which $tool 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missing += $tool
    }
}
if ($missing.Count -gt 0) {
    Write-Err "Missing tools in WSL: $($missing -join ', ')"
    Write-Host "  Run inside WSL:"
    Write-Host "  sudo apt install debootstrap parted dosfstools e2fsprogs"
    exit 1
}
Write-Log "WSL2 prerequisites OK"

# ── WiFi configuration ──────────────────────────────────────────────────────

Write-Section "WiFi configuration"

$wifiNetworks = @()
$useSaved = $false

if (Test-Path $WifiYaml) {
    $wifiConfig = Get-Content $WifiYaml -Raw | ConvertFrom-Yaml
    if ($wifiConfig.networks -and $wifiConfig.networks.Count -gt 0) {
        Write-Info "Saved WiFi networks found in wifi.yaml:"
        foreach ($net in $wifiConfig.networks) {
            Write-Host "    - $($net.ssid)"
        }
        Write-Host ""
        $answer = Read-Host "Use saved WiFi config? [Y/n]"
        if ($answer -eq '' -or $answer -match '^[Yy]') {
            $wifiNetworks = $wifiConfig.networks
            $useSaved = $true
            Write-Log "$($wifiNetworks.Count) WiFi network(s) loaded from wifi.yaml"
        }
    }
}

if (-not $useSaved) {
    Write-Host "Enter WiFi networks (blank SSID to stop)."
    Write-Host ""

    $index = 1
    while ($true) {
        $ssid = Read-Host "SSID $index"
        if ([string]::IsNullOrWhiteSpace($ssid)) { break }

        $psk = Read-Host "Password" -MaskInput

        $wifiNetworks += @{ ssid = $ssid; psk = $psk }
        $index++
    }

    if ($wifiNetworks.Count -eq 0) {
        Write-Err "At least one WiFi network is required"
        exit 1
    }

    # Save to wifi.yaml
    $yamlContent = @{ networks = $wifiNetworks } | ConvertTo-Yaml
    Set-Content -Path $WifiYaml -Value $yamlContent -Encoding UTF8 -NoNewline
    Write-Log "WiFi config saved to wifi.yaml ($($wifiNetworks.Count) network(s))"
}

# ── Tailscale configuration ─────────────────────────────────────────────────

Write-Section "Tailscale configuration"

$tsAuthKey = Read-Host "Tailscale Auth Key (reusable)" -MaskInput
if ([string]::IsNullOrWhiteSpace($tsAuthKey)) {
    Write-Err "Tailscale auth key is required"
    exit 1
}
Write-Log "Tailscale auth key set"

# ── K3s cluster (auto-fetch from GCP node via Tailscale) ─────────────────────

Write-Section "K3s cluster (GCP control plane)"

Write-Info "Fetching K3s server IP from k3s-control-0 via Tailscale..."

$k3sIp = $null
try { $k3sIp = (tailscale ssh root@k3s-control-0 -- tailscale ip -4 2>$null) | Select-Object -First 1 } catch {}
if ([string]::IsNullOrWhiteSpace($k3sIp)) {
    Write-Err "Failed to reach k3s-control-0 via Tailscale SSH"
    Write-Host "  Ensure k3s-control-0 is running and Tailscale ACLs allow SSH"
    exit 1
}
$k3sIp = $k3sIp.Trim()
$k3sServerUrl = "https://${k3sIp}:6443"
Write-Log "K3s server URL: $k3sServerUrl"

Write-Info "Fetching K3s join token..."
$k3sToken = $null
try { $k3sToken = (tailscale ssh root@k3s-control-0 -- cat /var/lib/rancher/k3s/server/node-token 2>$null) | Select-Object -First 1 } catch {}
if ([string]::IsNullOrWhiteSpace($k3sToken)) {
    Write-Err "Failed to fetch K3s token from k3s-control-0"
    Write-Host "  Ensure K3s server is running on the GCP node"
    exit 1
}
$k3sToken = $k3sToken.Trim()
Write-Log "K3s token fetched"

# ── Summary ──────────────────────────────────────────────────────────────────

Write-Section "Build summary"

Write-Info "Image label:    $NodeName"
Write-Info "Hostname:       (derived from MAC at first boot)"
Write-Info "WiFi networks:  $($wifiNetworks.Count)"
Write-Info "K3s server:     $k3sServerUrl"
if ($ImageOnly) {
    Write-Info "Target:         Image file (--image-only)"
} elseif ($Target) {
    Write-Info "Target:         $Target"
} else {
    Write-Err "No target specified. Use -ImageOnly or provide a device path."
    exit 1
}
Write-Host ""

# ── Build WiFi networks env var (newline-separated ssid|psk) ─────────────────

$wifiEnvLines = @()
foreach ($net in $wifiNetworks) {
    $wifiEnvLines += "$($net.ssid)|$($net.psk)"
}
$wifiEnvValue = $wifiEnvLines -join "`n"

# ── Convert Windows paths to WSL paths ───────────────────────────────────────

Write-Section "Delegating build to WSL2"

$wslRepoRoot = (wsl -d $WslDistro -- wslpath -u ($RepoRoot -replace '\\','/')) 2>&1 |
    Where-Object { $_ -is [string] } |
    Select-Object -First 1

$wslScriptPath = "$wslRepoRoot/kubernetes/scripts/bootable.sh"

Write-Info "WSL repo path: $wslRepoRoot"
Write-Info "WSL script:    $wslScriptPath"

# Build the bootable.sh arguments
$shArgs = @($NodeName)
if ($ImageOnly) {
    $shArgs += '--image-only'
} elseif ($Target) {
    $shArgs += $Target
}
if ($RebuildCache) {
    $shArgs += '--rebuild-cache'
}

$shArgsStr = ($shArgs | ForEach-Object { "'$_'" }) -join ' '

# Build the env var export block — use a temp script to avoid shell escaping issues
# with special characters in passwords and auth keys
$envScript = @"
#!/bin/bash
export BOOTABLE_NON_INTERACTIVE=1
export BOOTABLE_TS_AUTH_KEY='$($tsAuthKey -replace "'","'\''")'
export BOOTABLE_K3S_SERVER_URL='$($k3sServerUrl -replace "'","'\''")'
export BOOTABLE_K3S_TOKEN='$($k3sToken -replace "'","'\''")'
export BOOTABLE_WIFI_NETWORKS='$($wifiEnvValue -replace "'","'\''")'
cd '$wslRepoRoot/kubernetes/scripts'
exec bash bootable.sh $shArgsStr
"@

# Write env script to a temp file, convert to WSL path, execute
$tmpFile = [System.IO.Path]::GetTempFileName()
# Ensure LF line endings (not CRLF)
[System.IO.File]::WriteAllText($tmpFile, ($envScript -replace "`r`n", "`n"))

$wslTmpFile = (wsl -d $WslDistro -- wslpath -u ($tmpFile -replace '\\','/')) 2>&1 |
    Where-Object { $_ -is [string] } |
    Select-Object -First 1

Write-Info "Starting build..."
Write-Host ""

try {
    wsl -d $WslDistro -- sudo bash $wslTmpFile
    $buildExitCode = $LASTEXITCODE
} finally {
    # Clean up temp file
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
}

if ($buildExitCode -ne 0) {
    Write-Err "Build failed (exit code: $buildExitCode)"
    exit $buildExitCode
}

# ── Post-build instructions ──────────────────────────────────────────────────

if ($ImageOnly) {
    $imgPath = "$wslRepoRoot/kubernetes/cache/images/$NodeName.img"
    # Convert WSL path back to Windows
    $winImgPath = (wsl -d $WslDistro -- wslpath -w $imgPath) 2>&1 |
        Where-Object { $_ -is [string] } |
        Select-Object -First 1

    Write-Host ""
    Write-Section "Image ready"
    Write-Log "Image: $winImgPath"
    Write-Host ""
    Write-Host "Write to USB/SSD using one of these tools:"
    Write-Host "  - Rufus:         https://rufus.ie (DD mode)"
    Write-Host "  - balenaEtcher:  https://etcher.balena.io"
    Write-Host "  - Win32DiskImager"
    Write-Host ""
    Write-Host "Or from WSL:"
    Write-Host "  sudo dd if=$imgPath of=/dev/sdX bs=4M status=progress conv=fsync"
}

Write-Host ""
Write-Info "This is a generic image — flash to a single USB, reuse for all nodes."
Write-Host ""
Write-Info "Next steps (per node):"
Write-Info "  1. Flash image to USB"
Write-Info "  2. Boot laptop from USB"
Write-Info "  3. Node joins WiFi -> Tailscale (node-XXXXXX) -> K3s cluster"
Write-Info "  4. Clone USB to internal drive:"
Write-Info "       lsblk                          # identify internal drive"
Write-Info "       dd if=/dev/sda of=/dev/nvme0n1 bs=4M status=progress conv=fsync"
Write-Info "  5. Reboot, change BIOS boot order to internal drive"
Write-Info "  6. Remove USB — reuse it for the next node"
Write-Info "  Root partition auto-expands to fill the internal drive on next boot."
Write-Host ""
Write-Info "Verify: tailscale ssh root@k3s-control-0 -- k3s kubectl get nodes"

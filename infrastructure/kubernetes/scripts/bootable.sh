#!/usr/bin/env bash
# bootable.sh — Create a disk image for K3s worker nodes (WiFi + Tailscale)
#
# Builds a Debian 12 amd64 root filesystem with:
# - WiFi (wpasupplicant + firmware-iwlwifi), multiple SSIDs supported
# - Tailscale VPN (auto-joins tailnet on first boot)
# - SSH key auth (no password)
# - Lid-close suspend disabled (laptop runs headless with lid shut)
# - First-boot partition expand
# - GRUB EFI boot
#
# K3s is NOT installed here — use pool.sh after Tailscale connectivity is verified.
#
# Usage: sudo ./bootable.sh [node-name] <device-or-file> [--rebuild-cache]
#   e.g.: sudo ./bootable.sh /dev/sdb                 # Write generic image to SSD/USB
#         sudo ./bootable.sh --image-only              # Create generic .img file
#         sudo ./bootable.sh --image-only --rebuild-cache
#
# Node name is optional — defaults to "k3s-node" (image filename only).
# Hostname is derived from MAC address at first boot (node-{mac6}).
#
# Caching: The base rootfs (debootstrap + packages + GRUB) is cached as tarballs
# after the first build. Subsequent runs extract from cache (~1 min vs ~30 min).
# Use --rebuild-cache to force a full rebuild.
#
# Prerequisites: debootstrap, qemu-user-static, parted, dosfstools, e2fsprogs
#   sudo apt install debootstrap qemu-user-static parted dosfstools e2fsprogs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${SCRIPT_DIR}/../cache"

IMAGE_SIZE="8G"  # Minimum image size (expands on first boot)

ROOTFS_CACHE="${CACHE_DIR}/rootfs-bookworm-amd64.tar"
EFI_CACHE="${CACHE_DIR}/efi-bookworm-amd64.tar"

START_TIME=$(date +%s)

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${GREEN}[OK]${NC}     $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $*"; }
info()    { echo -e "${CYAN}[INFO]${NC}   $*"; }
err()     { echo -e "${RED}[ERROR]${NC}  $*" >&2; }
section() { echo -e "\n${BOLD}━━━ $* ━━━${NC}\n"; }

elapsed() {
    local now=$(date +%s)
    local secs=$((now - START_TIME))
    printf '%dm%02ds' $((secs / 60)) $((secs % 60))
}

# ---------- Argument parsing ----------

REBUILD_CACHE=false
IMAGE_ONLY=false
NODE_NAME=""
TARGET=""

# Collect positional and flag arguments
POSITIONALS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rebuild-cache) REBUILD_CACHE=true; shift ;;
        --image-only)    IMAGE_ONLY=true; shift ;;
        -h|--help)
            echo "Usage: sudo $0 [node-name] <device-or-file> [--rebuild-cache]"
            echo ""
            echo "  [node-name]      Optional label for image filename (default: k3s-node)"
            echo "  <device>         Write directly to block device (e.g. /dev/sdb)"
            echo "  --image-only     Create .img file in cache/images/ without writing"
            echo "  --rebuild-cache  Force rebuild of cached rootfs tarballs"
            echo ""
            echo "Hostname is derived from MAC address at first boot (node-XXXXXX)."
            exit 0
            ;;
        *)               POSITIONALS+=("$1"); shift ;;
    esac
done

# Parse positionals: [node-name] [<device>]
# Node name is optional — defaults to "k3s-node" (used only for the image filename).
NODE_NAME="k3s-node"

if [ "${IMAGE_ONLY}" = "true" ]; then
    # Optional node name for image filename
    if [ ${#POSITIONALS[@]} -ge 1 ]; then
        NODE_NAME="${POSITIONALS[0]}"
    fi
    mkdir -p "${CACHE_DIR}/images"
    TARGET="${CACHE_DIR}/images/${NODE_NAME}.img"
elif [ ${#POSITIONALS[@]} -ge 2 ]; then
    NODE_NAME="${POSITIONALS[0]}"
    TARGET="${POSITIONALS[1]}"
elif [ ${#POSITIONALS[@]} -ge 1 ]; then
    # Single arg — could be a device or a node name
    if [ -b "${POSITIONALS[0]}" ]; then
        TARGET="${POSITIONALS[0]}"
    else
        err "${POSITIONALS[0]} is not a block device"
        echo "Usage: sudo $0 [node-name] <device-or-file> [--rebuild-cache]"
        exit 1
    fi
else
    err "Missing target device (or use --image-only)"
    echo "Usage: sudo $0 [node-name] <device-or-file> [--rebuild-cache]"
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    err "Must run as root"
    exit 1
fi

# ---------- Non-interactive mode (env vars from bootable.ps1) ----------
# When BOOTABLE_NON_INTERACTIVE=1, all prompts are skipped and values come
# from environment variables. This is used by the PowerShell wrapper on Windows.

NI="${BOOTABLE_NON_INTERACTIVE:-0}"

# ---------- Check prerequisites ----------

for cmd in debootstrap parted mkfs.ext4 mkfs.vfat; do
    if ! command -v "$cmd" &>/dev/null; then
        err "${cmd} not found. Install prerequisites:"
        echo "  sudo apt install debootstrap qemu-user-static parted dosfstools e2fsprogs"
        exit 1
    fi
done

# ========== Interactive prompts ==========

WIFI_NETWORKS=()

if [ "${NI}" = "1" ] && [ -n "${BOOTABLE_WIFI_NETWORKS:-}" ]; then
    # Non-interactive: parse newline-separated ssid|psk pairs from env var
    while IFS= read -r line; do
        [ -n "${line}" ] && WIFI_NETWORKS+=("${line}")
    done <<< "${BOOTABLE_WIFI_NETWORKS}"
    log "${#WIFI_NETWORKS[@]} WiFi network(s) from environment."
else
    section "WiFi Configuration"
    echo "Enter WiFi networks (blank SSID to stop)."
    echo ""

    WIFI_INDEX=1
    while true; do
        read -rp "SSID ${WIFI_INDEX}: " ssid
        if [ -z "${ssid}" ]; then
            break
        fi
        read -rsp "Password: " psk
        echo ""
        WIFI_NETWORKS+=("${ssid}|${psk}")
        WIFI_INDEX=$((WIFI_INDEX + 1))
    done
fi

if [ ${#WIFI_NETWORKS[@]} -eq 0 ]; then
    err "At least one WiFi network is required"
    exit 1
fi
log "${#WIFI_NETWORKS[@]} WiFi network(s) configured."
echo ""

if [ "${NI}" = "1" ] && [ -n "${BOOTABLE_TS_AUTH_KEY:-}" ]; then
    TS_AUTH_KEY="${BOOTABLE_TS_AUTH_KEY}"
else
    section "Tailscale Configuration"
    read -rsp "Auth Key: " TS_AUTH_KEY
    echo ""
    if [ -z "${TS_AUTH_KEY}" ]; then
        err "Tailscale auth key is required"
        exit 1
    fi
    echo ""
fi

if [ "${NI}" = "1" ] && [ -n "${BOOTABLE_K3S_SERVER_URL:-}" ]; then
    K3S_SERVER_URL="${BOOTABLE_K3S_SERVER_URL}"
else
    section "K3s Cluster"
    read -rp "K3s server URL (e.g. https://100.x.y.z:6443): " K3S_SERVER_URL
    if [ -z "${K3S_SERVER_URL}" ]; then
        err "K3s server URL is required"
        exit 1
    fi
fi

if [ "${NI}" = "1" ] && [ -n "${BOOTABLE_K3S_TOKEN:-}" ]; then
    K3S_TOKEN="${BOOTABLE_K3S_TOKEN}"
else
    read -rsp "K3s join token: " K3S_TOKEN
    echo ""
    if [ -z "${K3S_TOKEN}" ]; then
        err "K3s join token is required"
        exit 1
    fi
    echo ""
fi

info "Image label:    ${NODE_NAME}"
info "Hostname:       (derived from MAC at first boot)"
info "WiFi networks:  ${#WIFI_NETWORKS[@]}"
info "K3s server:     ${K3S_SERVER_URL}"
info "Target:         ${TARGET}"
if [ -f "${ROOTFS_CACHE}" ] && [ -f "${EFI_CACHE}" ] && [ "${REBUILD_CACHE}" != "true" ]; then
    info "Cache:          ${GREEN}hit${NC} (will extract from cache)"
else
    info "Cache:          ${YELLOW}miss${NC} (full build required)"
fi
echo ""

# ---------- Confirmation for block devices ----------

if [ "${IMAGE_ONLY}" != "true" ]; then
    if [ ! -b "${TARGET}" ]; then
        err "${TARGET} is not a block device"
        echo "  Use --image-only to create a .img file instead"
        exit 1
    fi
    if [ "${NI}" != "1" ]; then
        echo -e "${YELLOW}WARNING: This will ERASE ${TARGET}!${NC}"
        read -rp "Type YES to continue: " confirm
        if [ "${confirm}" != "YES" ]; then
            echo "Aborted."
            exit 1
        fi
    fi
fi

# ---------- Create image file (if --image-only) ----------

LOOP_DEV=""
WORKDIR=$(mktemp -d)

cleanup() {
    info "Cleaning up..."
    umount "${WORKDIR}/rootfs/boot/efi" 2>/dev/null || true
    umount "${WORKDIR}/rootfs/dev/pts" 2>/dev/null || true
    umount "${WORKDIR}/rootfs/dev" 2>/dev/null || true
    umount "${WORKDIR}/rootfs/proc" 2>/dev/null || true
    umount "${WORKDIR}/rootfs/sys" 2>/dev/null || true
    umount "${WORKDIR}/rootfs/etc/resolv.conf" 2>/dev/null || true
    umount "${WORKDIR}/rootfs" 2>/dev/null || true
    [ -n "${LOOP_DEV}" ] && losetup -d "${LOOP_DEV}" 2>/dev/null || true
    rm -rf "${WORKDIR}"
}
trap cleanup EXIT

DISK="${TARGET}"
if [ "${IMAGE_ONLY}" = "true" ]; then
    info "Creating ${IMAGE_SIZE} disk image..."
    truncate -s "${IMAGE_SIZE}" "${TARGET}"
    DISK="${TARGET}"
fi

# ---------- Partition the disk ----------

section "Partitioning"

if [ "${IMAGE_ONLY}" = "true" ]; then
    LOOP_DEV=$(losetup --find --show --partscan "${DISK}")
    DISK_DEV="${LOOP_DEV}"
else
    DISK_DEV="${DISK}"
    wipefs -a "${DISK_DEV}" >/dev/null 2>&1 || true
fi

parted -s "${DISK_DEV}" \
    mklabel gpt \
    mkpart ESP fat32 1MiB 513MiB \
    set 1 esp on \
    mkpart root ext4 513MiB 100%

sleep 2
partprobe "${DISK_DEV}" 2>/dev/null || true
sleep 1

# Determine partition device names
if [ -n "${LOOP_DEV}" ]; then
    EFI_PART="${LOOP_DEV}p1"
    ROOT_PART="${LOOP_DEV}p2"
else
    if [ -b "${DISK_DEV}1" ]; then
        EFI_PART="${DISK_DEV}1"
        ROOT_PART="${DISK_DEV}2"
    elif [ -b "${DISK_DEV}p1" ]; then
        EFI_PART="${DISK_DEV}p1"
        ROOT_PART="${DISK_DEV}p2"
    else
        err "Could not find partition devices"
        exit 1
    fi
fi

info "Formatting partitions..."
mkfs.vfat -F 32 -n EFI "${EFI_PART}"
mkfs.ext4 -L root -F "${ROOT_PART}"

log "Partitioning complete ($(elapsed))"

# ---------- Mount ----------

ROOTFS="${WORKDIR}/rootfs"
mkdir -p "${ROOTFS}"
mount "${ROOT_PART}" "${ROOTFS}"
mkdir -p "${ROOTFS}/boot/efi"
mount "${EFI_PART}" "${ROOTFS}/boot/efi"

# ============================================================
# Base rootfs: cache-or-build
# ============================================================

if [ -f "${ROOTFS_CACHE}" ] && [ -f "${EFI_CACHE}" ] && [ "${REBUILD_CACHE}" != "true" ]; then
    # ---------- CACHE HIT: extract from tarballs ----------
    section "Extracting rootfs from cache"

    info "Extracting rootfs tarball..."
    tar xf "${ROOTFS_CACHE}" -C "${ROOTFS}"

    info "Extracting EFI tarball..."
    tar xf "${EFI_CACHE}" -C "${ROOTFS}/boot/efi"

    log "Cache extracted ($(elapsed))"
else
    # ---------- CACHE MISS: full build under qemu ----------
    section "Building base rootfs (qemu — this takes ~25 min)"

    if [ "${REBUILD_CACHE}" = "true" ]; then
        warn "Cache rebuild forced with --rebuild-cache"
    fi

    HOST_ARCH=$(uname -m)
    if [ "${HOST_ARCH}" = "x86_64" ] || [ "${HOST_ARCH}" = "amd64" ]; then
        # Native build — single-stage debootstrap, no chroot second-stage needed
        info "Running debootstrap (Debian 12 bookworm, amd64) — native, single-stage..."
        debootstrap --arch=amd64 bookworm "${ROOTFS}" http://deb.debian.org/debian
    else
        # Cross build (e.g. aarch64 Pi) — two-stage with qemu
        info "Running debootstrap (Debian 12 bookworm, amd64) — cross-build from ${HOST_ARCH}..."
        if [ ! -f /usr/bin/qemu-x86_64-static ]; then
            err "qemu-x86_64-static not found (required for cross-arch debootstrap)"
            err "  Install: sudo apt install qemu-user-static"
            exit 1
        fi
        debootstrap --arch=amd64 --foreign bookworm "${ROOTFS}" http://deb.debian.org/debian
        cp /usr/bin/qemu-x86_64-static "${ROOTFS}/usr/bin/"
        chroot "${ROOTFS}" /debootstrap/debootstrap --second-stage
    fi
    log "Debootstrap complete ($(elapsed))"

    # On x86_64 hosts, disable binfmt_misc qemu-x86_64 handler if registered
    # (Docker Desktop registers it system-wide, causing all chroot binaries
    # to be routed through qemu unnecessarily — 100x slower)
    if [ "${HOST_ARCH}" = "x86_64" ] || [ "${HOST_ARCH}" = "amd64" ]; then
        if [ -f /proc/sys/fs/binfmt_misc/qemu-x86_64 ]; then
            warn "Disabling binfmt_misc qemu-x86_64 handler (not needed on native x86_64)"
            echo -1 > /proc/sys/fs/binfmt_misc/qemu-x86_64 2>/dev/null || true
        fi
    fi

    # Mount virtual filesystems for chroot
    mount --bind /dev "${ROOTFS}/dev"
    mount --bind /dev/pts "${ROOTFS}/dev/pts"
    mount -t proc proc "${ROOTFS}/proc"
    mount -t sysfs sys "${ROOTFS}/sys"

    # APT sources
    cat > "${ROOTFS}/etc/apt/sources.list" << 'SOURCES_EOF'
deb http://deb.debian.org/debian bookworm main contrib non-free-firmware
deb http://deb.debian.org/debian bookworm-updates main contrib non-free-firmware
deb http://security.debian.org/debian-security bookworm-security main contrib non-free-firmware
SOURCES_EOF

    # Timezone (direct symlink — no chroot needed)
    ln -sf /usr/share/zoneinfo/Asia/Tokyo "${ROOTFS}/etc/localtime"
    echo "Asia/Tokyo" > "${ROOTFS}/etc/timezone"

    # Temporary resolv.conf for package installation
    echo "nameserver 8.8.8.8" > "${ROOTFS}/etc/resolv.conf.tmp"
    mount --bind "${ROOTFS}/etc/resolv.conf.tmp" "${ROOTFS}/etc/resolv.conf"

    # Install packages (locales must be installed before locale-gen)
    info "Installing packages (qemu)..."
    chroot "${ROOTFS}" apt-get update -qq
    DEBIAN_FRONTEND=noninteractive chroot "${ROOTFS}" apt-get install -y -qq \
        linux-image-amd64 \
        grub-efi-amd64 \
        systemd-sysv \
        systemd-timesyncd \
        wpasupplicant \
        firmware-iwlwifi \
        firmware-realtek \
        firmware-atheros \
        firmware-brcm80211 \
        firmware-misc-nonfree \
        locales \
        open-iscsi \
        2>&1 | tail -5
    log "Packages installed ($(elapsed))"

    # Locale (after locales package is installed)
    echo "en_US.UTF-8 UTF-8" > "${ROOTFS}/etc/locale.gen"
    chroot "${ROOTFS}" locale-gen

    # User setup
    chroot "${ROOTFS}" useradd -m -s /bin/bash -G sudo pi

    # Install GRUB EFI binaries
    info "Installing GRUB..."
    chroot "${ROOTFS}" grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian --removable 2>/dev/null || true
    log "GRUB installed ($(elapsed))"

    # ── Generic system config (goes into cache) ──

    # systemd-networkd config for WiFi interface (DHCP)
    mkdir -p "${ROOTFS}/etc/systemd/network"
    cat > "${ROOTFS}/etc/systemd/network/20-wifi.network" << 'NET_EOF'
[Match]
Name=wl*

[Network]
DHCP=yes

[DHCPv4]
RouteMetric=600
NET_EOF

    # Wired ethernet (DHCP) if plugged in
    cat > "${ROOTFS}/etc/systemd/network/10-ethernet.network" << 'ETH_EOF'
[Match]
Name=en* eth*

[Network]
DHCP=yes

[DHCPv4]
RouteMetric=100
ETH_EOF

    # wpa_supplicant service unit
    cat > "${ROOTFS}/etc/systemd/system/wpa-supplicant-wifi.service" << 'WPA_SVC_EOF'
[Unit]
Description=WPA supplicant for WiFi
Wants=network-pre.target
Before=network-pre.target
After=dbus.service
BindsTo=sys-subsystem-net-devices-wlan0.device
After=sys-subsystem-net-devices-wlan0.device

[Service]
Type=simple
ExecStart=/sbin/wpa_supplicant -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
WPA_SVC_EOF

    # udev rule to rename WiFi interface to wlan0
    cat > "${ROOTFS}/etc/udev/rules.d/70-wifi-name.rules" << 'UDEV_EOF'
# If the WiFi interface is not called wlan0, create an alias
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ATTR{type}=="1", KERNEL=="wl*", NAME="wlan0"
UDEV_EOF

    # NTP server config (WiFi APs rarely provide NTP via DHCP)
    mkdir -p "${ROOTFS}/etc/systemd"
    cat > "${ROOTFS}/etc/systemd/timesyncd.conf" << 'NTP_EOF'
[Time]
NTP=time.google.com time.cloudflare.com
FallbackNTP=0.debian.pool.ntp.org 1.debian.pool.ntp.org 2.debian.pool.ntp.org
NTP_EOF

    # Laptop lid-close handling
    mkdir -p "${ROOTFS}/etc/systemd/logind.conf.d"
    cat > "${ROOTFS}/etc/systemd/logind.conf.d/lid-ignore.conf" << 'LID_EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
LID_EOF

    # Root password for console access (needed to run dd for USB-to-SSD clone)
    chroot "${ROOTFS}" bash -c 'echo "root:shinbee" | chpasswd'

    # Sudoers for pi
    mkdir -p "${ROOTFS}/etc/sudoers.d"
    echo "pi ALL=(ALL) NOPASSWD:ALL" > "${ROOTFS}/etc/sudoers.d/pi"
    chmod 440 "${ROOTFS}/etc/sudoers.d/pi"

    # SSH hardening (drop-in; read by openssh-server when it installs on first boot)
    mkdir -p "${ROOTFS}/etc/ssh/sshd_config.d"
    cat > "${ROOTFS}/etc/ssh/sshd_config.d/hardening.conf" << 'SSH_EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
SSH_EOF

    # First-boot expand partition script
    cat > "${ROOTFS}/usr/local/bin/expand-rootfs.sh" << 'EXPAND_EOF'
#!/bin/bash
# Expand root partition to fill the disk (runs every boot until done)
set -e
ROOT_DEV=$(findmnt -n -o SOURCE /)
DISK_DEV="/dev/$(lsblk -ndo PKNAME "${ROOT_DEV}" | head -1)"
PART_NUM=$(echo "${ROOT_DEV}" | grep -oE '[0-9]+$')

if [ -b "${DISK_DEV}" ] && [ -n "${PART_NUM}" ]; then
    echo ", +" | sfdisk --no-reread -N "${PART_NUM}" "${DISK_DEV}" 2>/dev/null || true
    partprobe "${DISK_DEV}" 2>/dev/null || partx -u "${DISK_DEV}" 2>/dev/null || true
    sleep 1
    resize2fs "${ROOT_DEV}" 2>/dev/null || true
fi

# Only disable once partition uses >90% of the disk
DISK_SIZE=$(lsblk -bndo SIZE "${DISK_DEV}")
PART_SIZE=$(lsblk -bndo SIZE "${ROOT_DEV}")
if [ -n "${DISK_SIZE}" ] && [ -n "${PART_SIZE}" ] && [ "${DISK_SIZE}" -gt 0 ]; then
    USAGE=$((PART_SIZE * 100 / DISK_SIZE))
    if [ "${USAGE}" -ge 90 ]; then
        systemctl disable expand-rootfs.service
    fi
fi
EXPAND_EOF
    chmod +x "${ROOTFS}/usr/local/bin/expand-rootfs.sh"

    cat > "${ROOTFS}/etc/systemd/system/expand-rootfs.service" << 'EXPAND_SVC_EOF'
[Unit]
Description=Expand root filesystem to fill disk
After=local-fs.target
ConditionPathExists=/usr/local/bin/expand-rootfs.sh

[Service]
Type=oneshot
ExecStart=/usr/local/bin/expand-rootfs.sh

[Install]
WantedBy=multi-user.target
EXPAND_SVC_EOF

    # node-provision service unit (generic — script is per-node, written later)
    cat > "${ROOTFS}/etc/systemd/system/node-provision.service" << 'PROVISION_SVC_EOF'
[Unit]
Description=First-boot node provisioning
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/node-provision.sh
RemainAfterExit=yes
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
PROVISION_SVC_EOF

    # Enable services via direct symlinks (no chroot systemctl needed)
    mkdir -p "${ROOTFS}/etc/systemd/system/multi-user.target.wants"
    ln -sf /lib/systemd/system/systemd-networkd.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/systemd-networkd.service"
    ln -sf /lib/systemd/system/systemd-resolved.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/systemd-resolved.service"
    ln -sf /lib/systemd/system/systemd-timesyncd.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/systemd-timesyncd.service"
    ln -sf /etc/systemd/system/wpa-supplicant-wifi.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/wpa-supplicant-wifi.service"
    ln -sf /etc/systemd/system/expand-rootfs.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/expand-rootfs.service"
    ln -sf /etc/systemd/system/node-provision.service \
        "${ROOTFS}/etc/systemd/system/multi-user.target.wants/node-provision.service"

    # Cleanup chroot
    info "Cleaning up chroot..."
    chroot "${ROOTFS}" apt-get clean
    rm -f "${ROOTFS}/usr/bin/qemu-x86_64-static"
    rm -rf "${ROOTFS}/tmp/"*

    # Unmount virtual filesystems
    umount "${ROOTFS}/etc/resolv.conf" 2>/dev/null || true
    rm -f "${ROOTFS}/etc/resolv.conf.tmp"
    umount "${ROOTFS}/sys"
    umount "${ROOTFS}/proc"
    umount "${ROOTFS}/dev/pts"
    umount "${ROOTFS}/dev"

    # ── Save cache tarballs ──
    section "Saving cache"

    mkdir -p "${CACHE_DIR}"

    info "Saving EFI cache..."
    tar cf "${EFI_CACHE}" -C "${ROOTFS}/boot/efi" .
    EFI_SIZE=$(du -h "${EFI_CACHE}" | awk '{print $1}')

    # Unmount EFI before saving rootfs tar (EFI is separate)
    umount "${ROOTFS}/boot/efi"

    info "Saving rootfs cache..."
    tar cf "${ROOTFS_CACHE}" -C "${ROOTFS}" .
    ROOTFS_SIZE=$(du -h "${ROOTFS_CACHE}" | awk '{print $1}')

    log "Cache saved: rootfs=${ROOTFS_SIZE}, efi=${EFI_SIZE} ($(elapsed))"

    # Re-mount EFI for per-node config phase
    mount "${EFI_PART}" "${ROOTFS}/boot/efi"
fi

# ============================================================
# Per-node config (every run — native file writes, no qemu)
# ============================================================

section "Applying image config"

# Placeholder hostname (overwritten by node-provision.sh on first boot)
echo "k3s-node" > "${ROOTFS}/etc/hostname"
cat > "${ROOTFS}/etc/hosts" << HOSTS_EOF
127.0.0.1   localhost
127.0.1.1   k3s-node
HOSTS_EOF

# fstab (with actual partition UUIDs)
ROOT_UUID=$(blkid -s UUID -o value "${ROOT_PART}")
EFI_UUID=$(blkid -s UUID -o value "${EFI_PART}")
cat > "${ROOTFS}/etc/fstab" << FSTAB_EOF
UUID=${ROOT_UUID}   /           ext4    errors=remount-ro   0   1
UUID=${EFI_UUID}    /boot/efi   vfat    umask=0077          0   2
FSTAB_EOF

# wpa_supplicant.conf with all prompted SSIDs
mkdir -p "${ROOTFS}/etc/wpa_supplicant"
cat > "${ROOTFS}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf" << 'WPA_HEADER'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=JP
WPA_HEADER

for entry in "${WIFI_NETWORKS[@]}"; do
    ssid="${entry%%|*}"
    psk="${entry#*|}"
    if command -v wpa_passphrase &>/dev/null; then
        wpa_passphrase "${ssid}" "${psk}" | grep -v '#psk' >> "${ROOTFS}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
    else
        cat >> "${ROOTFS}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf" << NETWORK_EOF

network={
    ssid="${ssid}"
    psk="${psk}"
}
NETWORK_EOF
    fi
done
chmod 600 "${ROOTFS}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"

# SSH keypair — auto-generated at first boot, no external injection.
# Access is via Tailscale SSH. Traditional SSH is a fallback only.
mkdir -p "${ROOTFS}/root/.ssh" "${ROOTFS}/home/pi/.ssh"
chmod 700 "${ROOTFS}/root/.ssh" "${ROOTFS}/home/pi/.ssh"
chown -R 1000:1000 "${ROOTFS}/home/pi/.ssh"

# node-provision.sh (generic: derives hostname from MAC, joins K3s cluster)
cat > "${ROOTFS}/usr/local/bin/node-provision.sh" << PROVISION_EOF
#!/bin/bash
# node-provision.sh — First-boot provisioning (runs natively on x86)
set -euo pipefail
export HOME="${HOME:-/root}"
exec &> >(tee -a /var/log/node-provision.log)

echo "[provision] Started at \$(date)"

# 0. Derive hostname from primary NIC MAC address
#    Picks the first non-lo, non-virtual interface with a MAC
MAC=\$(ip -o link show | awk -F': ' '!/lo|vir|docker/{print \$2; exit}')
MAC_ADDR=\$(cat /sys/class/net/"\${MAC}"/address 2>/dev/null || echo "")
if [ -n "\${MAC_ADDR}" ]; then
    # Last 3 octets, no colons → node-a1b2c3
    MAC_HASH=\$(echo "\${MAC_ADDR}" | awk -F: '{printf "%s%s%s", \$4, \$5, \$6}')
    NODE_HOSTNAME="node-\${MAC_HASH}"
else
    NODE_HOSTNAME="node-\$(head -c4 /dev/urandom | xxd -p)"
fi
echo "\${NODE_HOSTNAME}" > /etc/hostname
hostname "\${NODE_HOSTNAME}"
sed -i "s/127.0.1.1.*/127.0.1.1   \${NODE_HOSTNAME}/" /etc/hosts
echo "[provision] Hostname set to \${NODE_HOSTNAME}"

# Wait for DNS to become available (WiFi + DHCP may still be settling)
echo "[provision] Waiting for network (DNS)..."
for i in \$(seq 1 60); do
    if getent hosts deb.debian.org >/dev/null 2>&1; then
        echo "[provision] Network ready (attempt \${i})"
        break
    fi
    sleep 2
done

# Sync clock via NTP (hardware clock may be wrong, APT rejects future dates)
timedatectl set-ntp true 2>/dev/null || true
for i in \$(seq 1 15); do
    if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
        echo "[provision] Clock synced via NTP"
        break
    fi
    sleep 2
done

# 1. Generate SSH keypair (access is via Tailscale SSH, this is fallback)
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -q 2>/dev/null || true
su - pi -c "ssh-keygen -t ed25519 -f /home/pi/.ssh/id_ed25519 -N '' -q" 2>/dev/null || true

# 2. Install deferred packages
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    openssh-server sudo curl jq ca-certificates gnupg cloud-guest-utils \
    open-iscsi nfs-common parted

# 3. Tailscale
curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian bookworm main" \
    > /etc/apt/sources.list.d/tailscale.list
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tailscale
systemctl enable --now tailscaled
tailscale up --authkey=${TS_AUTH_KEY} --hostname=\${NODE_HOSTNAME} --ssh

# Wait for Tailscale IP
for i in \$(seq 1 30); do
    TS_IP=\$(tailscale ip -4 2>/dev/null || true)
    [ -n "\${TS_IP}" ] && break
    sleep 2
done
echo "[provision] Tailscale IP: \${TS_IP:-FAILED}"

# Wait for Tailscale SSH to become ready (key exchange + ACL sync)
echo "[provision] Waiting for Tailscale SSH to k3s-control-0..."
TS_SSH_OK=0
for attempt in \$(seq 1 60); do
    if tailscale ssh root@k3s-control-0 -- echo "tailscale-ssh-ok" < /dev/null 2>&1 | grep -q "tailscale-ssh-ok"; then
        echo "[provision] Tailscale SSH ready (attempt \${attempt})"
        TS_SSH_OK=1
        break
    else
        TS_SSH_ERR=\$(tailscale ssh root@k3s-control-0 -- echo "test" < /dev/null 2>&1 || true)
        echo "[provision] Tailscale SSH not ready (\${attempt}/60): \${TS_SSH_ERR}"
    fi
    sleep 5
done
if [ "\${TS_SSH_OK}" -ne 1 ]; then
    echo "[provision] ERROR: Tailscale SSH to k3s-control-0 never became ready after 5 minutes"
    echo "[provision] tailscale status:"
    tailscale status 2>&1 || true
fi

# 4. Fetch registries.yaml from GCP node (Artifact Registry auth)
mkdir -p /etc/rancher/k3s
echo "[provision] Fetching registries.yaml from k3s-control-0..."
REGISTRIES_OK=0
for attempt in \$(seq 1 30); do
    # Write to temp file — don't clobber target with stderr on failure
    FETCH_ERR=\$(tailscale ssh root@k3s-control-0 -- cat /etc/rancher/k3s/registries.yaml < /dev/null > /tmp/registries.yaml 2>&1)
    FETCH_RC=\$?
    if [ "\${FETCH_RC}" -eq 0 ]; then
        # Validate it looks like YAML, not an error message
        if grep -q "^mirrors:" /tmp/registries.yaml 2>/dev/null; then
            mv /tmp/registries.yaml /etc/rancher/k3s/registries.yaml
            chmod 600 /etc/rancher/k3s/registries.yaml
            echo "[provision] registries.yaml fetched (attempt \${attempt}, \$(wc -c < /etc/rancher/k3s/registries.yaml) bytes)"
            REGISTRIES_OK=1
            break
        else
            echo "[provision] registries.yaml fetch returned data but missing 'mirrors:' header (attempt \${attempt})"
            echo "[provision]   content preview: \$(head -3 /tmp/registries.yaml 2>/dev/null)"
        fi
    else
        echo "[provision] registries.yaml fetch failed (attempt \${attempt}/30, rc=\${FETCH_RC}): \${FETCH_ERR}"
    fi
    rm -f /tmp/registries.yaml
    sleep 10
done

if [ "\${REGISTRIES_OK}" -ne 1 ]; then
    echo "[provision] WARNING: Could not fetch registries.yaml — K3s will start without AR auth"
    echo "[provision] Last tailscale status:"
    tailscale status 2>&1 || true
    rm -f /etc/rancher/k3s/registries.yaml
fi

# 5. K3s agent — join the GCP control plane via Tailscale
curl -sfL https://get.k3s.io | \\
    INSTALL_K3S_EXEC="agent" \\
    K3S_URL="${K3S_SERVER_URL}" \\
    K3S_TOKEN="${K3S_TOKEN}" \\
    INSTALL_K3S_CHANNEL="stable" \\
    sh -s - \\
    --node-ip="\${TS_IP}" \\
    --flannel-iface=tailscale0

# Wait for k3s-agent to start successfully
echo "[provision] Waiting for k3s-agent to connect..."
sleep 10

# Check for node password rejection (happens when node was reflashed)
if journalctl -u k3s-agent --no-pager -n 20 2>/dev/null | grep -q "Node password rejected"; then
    echo "[provision] Node password rejected — this node was previously registered"
    echo "[provision] Cleaning up stale registration on server..."

    # Delete the old node from the K3s server
    tailscale ssh root@k3s-control-0 -- k3s kubectl delete node "\${NODE_HOSTNAME}" < /dev/null 2>&1 || true
    echo "[provision] Deleted old node '\${NODE_HOSTNAME}' from server"

    # Remove local stale credentials
    rm -f /etc/rancher/node/password
    rm -f /var/lib/rancher/k3s/agent/client-ca.crt
    rm -f /var/lib/rancher/k3s/agent/client-kubelet.crt
    rm -f /var/lib/rancher/k3s/agent/client-kubelet.key
    rm -f /var/lib/rancher/k3s/agent/serving-kubelet.crt
    rm -f /var/lib/rancher/k3s/agent/serving-kubelet.key

    echo "[provision] Restarting k3s-agent with clean state..."
    systemctl restart k3s-agent
    sleep 10

    if journalctl -u k3s-agent --no-pager -n 10 2>/dev/null | grep -q "Node password rejected"; then
        echo "[provision] ERROR: k3s-agent still rejected after cleanup"
        journalctl -u k3s-agent --no-pager -n 20 || true
    else
        echo "[provision] k3s-agent re-registered successfully"
    fi
fi

# Verify agent is running
if systemctl is-active --quiet k3s-agent; then
    echo "[provision] k3s-agent running — joined cluster at ${K3S_SERVER_URL}"
else
    echo "[provision] WARNING: k3s-agent not running"
    journalctl -u k3s-agent --no-pager -n 10 || true
fi

# 6. Self-disable
systemctl disable node-provision.service

echo "[provision] Complete at \$(date)"
PROVISION_EOF
chmod +x "${ROOTFS}/usr/local/bin/node-provision.sh"

# resolv.conf — static fallback, then systemd-resolved takes over at runtime
rm -f "${ROOTFS}/etc/resolv.conf" 2>/dev/null || true
cat > "${ROOTFS}/etc/resolv.conf" << 'RESOLV_EOF'
nameserver 8.8.8.8
nameserver 8.8.4.4
RESOLV_EOF

# GRUB config (templated — no chroot update-grub needed)
KERNEL_VERSION=$(ls "${ROOTFS}/boot/" | grep -oP 'vmlinuz-\K.*' | sort -V | tail -1)
if [ -z "${KERNEL_VERSION}" ]; then
    err "No kernel found in ${ROOTFS}/boot/"
    exit 1
fi

info "Kernel: ${KERNEL_VERSION}"

mkdir -p "${ROOTFS}/boot/grub"
cat > "${ROOTFS}/boot/grub/grub.cfg" << GRUB_EOF
set default=0
set timeout=5

menuentry "Debian GNU/Linux" {
    search --no-floppy --fs-uuid --set=root ${ROOT_UUID}
    linux /boot/vmlinuz-${KERNEL_VERSION} root=UUID=${ROOT_UUID} ro quiet
    initrd /boot/initrd.img-${KERNEL_VERSION}
}
GRUB_EOF

# EFI partition grub.cfg — GRUB EFI (--removable) looks here first,
# then chains to the main grub.cfg on the root partition
mkdir -p "${ROOTFS}/boot/efi/EFI/BOOT"
cat > "${ROOTFS}/boot/efi/EFI/BOOT/grub.cfg" << EFI_GRUB_EOF
search.fs_uuid ${ROOT_UUID} root
set prefix=(\$root)/boot/grub
configfile \$prefix/grub.cfg
EFI_GRUB_EOF

log "Per-node config applied ($(elapsed))"

# ---------- Finalize ----------

sync
umount "${ROOTFS}/boot/efi"
umount "${ROOTFS}"

if [ "${IMAGE_ONLY}" = "true" ]; then
    losetup -d "${LOOP_DEV}" 2>/dev/null || true
    LOOP_DEV=""

    IMG_SIZE=$(du -h "${TARGET}" | awk '{print $1}')

    section "Done ($(elapsed))"
    log "Image created: ${TARGET} (${IMG_SIZE})"
    echo ""
    echo "Write to USB/SSD:"
    echo "  sudo dd if=${TARGET} of=/dev/sdX bs=4M status=progress conv=fsync"
    echo ""
    echo "The root partition will auto-expand to fill the disk on first boot."
else
    section "Done ($(elapsed))"
fi

echo ""
info "Generic disk image is ready."
info "  Flash to multiple USBs — each node gets a unique hostname from its MAC"
info "  Boot the laptop → WiFi → Tailscale (as node-XXXXXX)"
info "  Then run pool.sh to install K3s"

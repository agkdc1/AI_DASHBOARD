#!/bin/bash
# =============================================================================
# Headless Asterisk entrypoint
# Runs confgen to generate initial configs, then starts Asterisk.
# =============================================================================
set -e

echo "=== Headless Asterisk starting ==="
echo "  Hostname: $(hostname)"
echo "  Date: $(date)"

# ---------------------------------------------------------------------------
# Generate configs from SQLite if pbx.db exists
# ---------------------------------------------------------------------------
PBX_DB="${PBX_DB_PATH:-/var/lib/asterisk/pbx.db}"
ASTERISK_DIR="/etc/asterisk"

if [ -f "$PBX_DB" ]; then
    echo "  PBX DB found: $PBX_DB"
    echo "  Running confgen..."
    python3 /opt/confgen.py --db "$PBX_DB" --output-dir "$ASTERISK_DIR" || {
        echo "WARNING: confgen failed, starting with existing configs"
    }
else
    echo "  WARNING: No PBX DB at $PBX_DB — using existing configs"
fi

# ---------------------------------------------------------------------------
# Verify critical config files exist
# ---------------------------------------------------------------------------
for conf in extensions.conf extensions_custom.conf pjsip.conf pjsip_ntt_dynamic.conf; do
    if [ ! -f "$ASTERISK_DIR/$conf" ]; then
        echo "  WARNING: Missing $ASTERISK_DIR/$conf"
    fi
done

# ---------------------------------------------------------------------------
# Add MetalLB VIP as local address (so Asterisk can bind to it)
# ---------------------------------------------------------------------------
if [ -n "${ASTERISK_VIP:-}" ]; then
    # Find the interface with a 10.0.x.x address (LAN)
    VIP_IF=$(ip -4 -o addr show | awk '/inet 10\.0\./{print $2; exit}')
    if [ -n "$VIP_IF" ]; then
        ip addr add "${ASTERISK_VIP}/32" dev "$VIP_IF" 2>/dev/null || true
        echo "  VIP $ASTERISK_VIP added on $VIP_IF"
    else
        echo "  WARNING: No 10.0.x.x interface found for VIP"
    fi
fi

# ---------------------------------------------------------------------------
# Fix ownership
# ---------------------------------------------------------------------------
chown -R asterisk:asterisk /var/log/asterisk /var/run/asterisk /var/spool/asterisk 2>/dev/null || true
chown asterisk:asterisk "$ASTERISK_DIR"/*.conf 2>/dev/null || true

# ---------------------------------------------------------------------------
# Fix HylaFAX config symlinks (init configs mounted at /etc/hylafax-init/)
# ---------------------------------------------------------------------------
if [ -d /etc/hylafax-init ]; then
    for f in setup.cache setup.modem config config.ttyIAX0; do
        if [ -f "/etc/hylafax-init/$f" ]; then
            cp "/etc/hylafax-init/$f" "/var/spool/hylafax/etc/$f" 2>/dev/null || true
            chown uucp:uucp "/var/spool/hylafax/etc/$f" 2>/dev/null || true
        fi
    done
fi

# ---------------------------------------------------------------------------
# Start IAXmodem if configured
# ---------------------------------------------------------------------------
if [ -f /etc/iaxmodem/ttyIAX0 ]; then
    echo "  Starting IAXmodem..."
    /usr/bin/iaxmodem ttyIAX0 &
    sleep 2
fi

# ---------------------------------------------------------------------------
# Start HylaFAX if configured
# ---------------------------------------------------------------------------
if [ -d /var/spool/hylafax/etc ]; then
    echo "  Starting HylaFAX..."
    /usr/sbin/faxq &
    /usr/sbin/hfaxd -i hylafax &
    if [ -f /etc/iaxmodem/ttyIAX0 ]; then
        echo "  Starting faxgetty on ttyIAX0..."
        /usr/sbin/faxgetty ttyIAX0 &
    fi
fi

# ---------------------------------------------------------------------------
# Start Asterisk in foreground
# ---------------------------------------------------------------------------
echo "  Starting Asterisk..."
exec /usr/sbin/asterisk -fvvv -U asterisk -G asterisk

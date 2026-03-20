#!/bin/bash
set -e

REALM="${SAMBA_REALM:-SHINBEE.LOCAL}"
DOMAIN="${SAMBA_DOMAIN:-SHINBEE}"
AD_DC_IP="${AD_DC_IP:-10.0.0.250}"

# Generate Kerberos config
cat > /etc/krb5.conf <<EOF
[libdefaults]
    default_realm = ${REALM}
    dns_lookup_realm = false
    dns_lookup_kdc = false

[realms]
    ${REALM} = {
        kdc = ${AD_DC_IP}
        admin_server = ${AD_DC_IP}
    }

[domain_realm]
    .$(echo "$REALM" | tr 'A-Z' 'a-z') = ${REALM}
    $(echo "$REALM" | tr 'A-Z' 'a-z') = ${REALM}
EOF

# Generate smb.conf
cat > /etc/samba/smb.conf <<EOF
[global]
    security = ads
    realm = ${REALM}
    workgroup = ${DOMAIN}
    idmap config * : backend = tdb
    idmap config * : range = 10000-99999
    idmap config ${DOMAIN} : backend = rid
    idmap config ${DOMAIN} : range = 100000-999999
    winbind use default domain = yes
    winbind enum users = yes
    winbind enum groups = yes
    template shell = /bin/bash
    template homedir = /home/%U
    vfs objects = acl_xattr
    map acl inherit = yes
    store dos attributes = yes

    log file = /var/log/samba/%m.log
    log level = 1

include = /etc/samba/smb-shares.conf
EOF

# Configure NSS for winbind
sed -i 's/^passwd:.*/passwd:         files winbind/' /etc/nsswitch.conf
sed -i 's/^group:.*/group:          files winbind/' /etc/nsswitch.conf

# Domain join (or verify existing)
if wbinfo -t 2>/dev/null; then
    echo "=== Domain trust OK, already joined ==="
else
    echo "=== Joining domain ${REALM}... ==="
    net ads join -U "Administrator%${SAMBA_ADMIN_PASSWORD}" || {
        echo "Domain join failed, retrying in 10s..."
        sleep 10
        net ads join -U "Administrator%${SAMBA_ADMIN_PASSWORD}"
    }
fi

# Ensure share directories exist with correct permissions
mkdir -p /srv/samba/profiles /srv/samba/shared
chmod 1770 /srv/samba/profiles
chmod 2770 /srv/samba/shared

# Generate supervisor config
cat > /etc/supervisor/conf.d/samba.conf <<EOF
[supervisord]
nodaemon=true
user=root

[program:winbindd]
command=/usr/sbin/winbindd -F --no-process-group
autostart=true
autorestart=true
priority=10

[program:smbd]
command=/usr/sbin/smbd -F --no-process-group
autostart=true
autorestart=true
priority=20
EOF

echo "Starting winbindd + smbd..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

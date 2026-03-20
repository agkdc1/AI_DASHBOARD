#!/bin/bash
set -e

REALM="${SAMBA_REALM:-AD.YOUR-DOMAIN.COM}"
DOMAIN="${SAMBA_DOMAIN:-AD}"
DNS_FORWARDER="${DNS_FORWARDER:-10.0.7.1}"
SAM_LDB="/var/lib/samba/private/sam.ldb"

if [ ! -f "$SAM_LDB" ]; then
    echo "=== First boot: provisioning Samba AD DC ==="

    # Remove default smb.conf so provision can write its own
    rm -f /etc/samba/smb.conf

    samba-tool domain provision \
        --realm="$REALM" \
        --domain="$DOMAIN" \
        --server-role=dc \
        --dns-backend=SAMBA_INTERNAL \
        --adminpass="$SAMBA_ADMIN_PASSWORD" \
        --option="dns forwarder = $DNS_FORWARDER"

    # Patch smb.conf for Grandstream phones (no LDAPS support) and internal use
    sed -i '/\[global\]/a \\tldap server require strong auth = no' /etc/samba/smb.conf

    # Copy Kerberos config
    cp /var/lib/samba/private/krb5.conf /etc/krb5.conf

    # Persist smb.conf to PVC (container filesystem is ephemeral)
    cp /etc/samba/smb.conf /var/lib/samba/smb.conf.provisioned

    echo "=== Provisioning complete ==="
else
    echo "=== Existing AD database found, starting Samba ==="
fi

# Restore provisioned smb.conf from PVC (lost on container restart)
if [ -f /var/lib/samba/smb.conf.provisioned ]; then
    cp /var/lib/samba/smb.conf.provisioned /etc/samba/smb.conf
    echo "Restored provisioned smb.conf from PVC"
elif [ -f "$SAM_LDB" ]; then
    # AD database exists but no saved smb.conf — regenerate minimal config
    echo "Regenerating smb.conf for existing AD database..."
    cat > /etc/samba/smb.conf <<SMBEOF
[global]
    dns forwarder = $DNS_FORWARDER
    netbios name = $(hostname -s | tr '[:lower:]' '[:upper:]')
    realm = $REALM
    server role = active directory domain controller
    workgroup = $DOMAIN
    ldap server require strong auth = no

[sysvol]
    path = /var/lib/samba/sysvol
    read only = No

[netlogon]
    path = /var/lib/samba/sysvol/${REALM,,}/scripts
    read only = No
SMBEOF
    cp /etc/samba/smb.conf /var/lib/samba/smb.conf.provisioned
    echo "Regenerated and saved smb.conf"
fi

# Ensure krb5.conf is current
if [ -f /var/lib/samba/private/krb5.conf ]; then
    cp /var/lib/samba/private/krb5.conf /etc/krb5.conf
fi

echo "Starting Samba AD DC (realm=$REALM, domain=$DOMAIN)..."
exec samba -F --no-process-group

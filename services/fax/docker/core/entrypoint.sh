#!/bin/bash
set -e

# FreePBX installs fwconsole to /var/lib/asterisk/bin
export PATH="/var/lib/asterisk/bin:${PATH}"

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${MYSQL_USER:-freepbxuser}"
DB_PASS="${MYSQL_PASSWORD}"
DB_NAME="${MYSQL_DATABASE:-asterisk}"

echo "=== RasPBX Core Container Starting ==="

# ---------------------------------------------------------------
# Wait for MariaDB to be ready
# ---------------------------------------------------------------
echo "Waiting for MariaDB at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 60); do
    if mariadb -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -e "SELECT 1" "$DB_NAME" >/dev/null 2>&1; then
        echo "MariaDB is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: MariaDB not ready after 60 seconds. Exiting."
        exit 1
    fi
    sleep 1
done

# ---------------------------------------------------------------
# Ensure /etc/freepbx.conf exists (required by fwconsole)
# ---------------------------------------------------------------
cat > /etc/freepbx.conf <<PHPEOF
<?php
\$amp_conf['AMPDBUSER'] = '${DB_USER}';
\$amp_conf['AMPDBPASS'] = '${DB_PASS}';
\$amp_conf['AMPDBHOST'] = '${DB_HOST}';
\$amp_conf['AMPDBPORT'] = '${DB_PORT}';
\$amp_conf['AMPDBNAME'] = '${DB_NAME}';
\$amp_conf['AMPDBENGINE'] = 'mysql';
\$amp_conf['datasource'] = '';

require_once('/var/www/html/admin/bootstrap.php');
?>
PHPEOF
chmod 640 /etc/freepbx.conf
chown asterisk:asterisk /etc/freepbx.conf

# ---------------------------------------------------------------
# First-run: Install FreePBX if not yet installed
# ---------------------------------------------------------------
if [ ! -f /var/www/html/admin/bootstrap.php ]; then
    echo "First run detected — installing FreePBX..."

    cd /usr/src/freepbx

    # Start Asterisk temporarily for FreePBX install
    /usr/sbin/asterisk -U asterisk -G asterisk
    sleep 3

    ./install -n \
        --dbhost="$DB_HOST" \
        --dbuser="$DB_USER" \
        --dbpass="$DB_PASS" \
        --dbname="$DB_NAME" \
        --webroot=/var/www/html \
        --astetcdir=/etc/asterisk \
        --astmoddir=/usr/lib/asterisk/modules \
        --astvarlibdir=/var/lib/asterisk \
        --astagidir=/var/lib/asterisk/agi-bin \
        --astspooldir=/var/spool/asterisk \
        --astrundir=/var/run/asterisk \
        --astlogdir=/var/log/asterisk

    # Install modules
    fwconsole ma installall
    fwconsole reload
    fwconsole chown

    # Stop temp Asterisk (supervisord will start it properly)
    asterisk -rx "core stop now" 2>/dev/null || true
    sleep 2

    echo "FreePBX installation complete."
else
    echo "FreePBX already installed, running chown..."
    fwconsole chown || echo "WARNING: fwconsole chown failed (non-fatal)"
fi

# ---------------------------------------------------------------
# Fix permissions
# ---------------------------------------------------------------
chown -R asterisk:asterisk /var/www/html /var/lib/asterisk \
    /var/spool/asterisk /var/log/asterisk /var/run/asterisk \
    /etc/asterisk 2>/dev/null || true

# Ensure PHP-FPM socket directory exists
mkdir -p /run/php
# Ensure supervisor log directory exists
mkdir -p /var/log/supervisor

# Fix PHP-FPM to run as asterisk (FreePBX owns all files as asterisk:asterisk)
sed -i 's/^user = www-data/user = asterisk/' /etc/php/8.2/fpm/pool.d/www.conf
sed -i 's/^group = www-data/group = asterisk/' /etc/php/8.2/fpm/pool.d/www.conf
sed -i 's/^listen.owner = www-data/listen.owner = asterisk/' /etc/php/8.2/fpm/pool.d/www.conf
sed -i 's/^listen.group = www-data/listen.group = www-data/' /etc/php/8.2/fpm/pool.d/www.conf
sed -i 's/^listen.mode = .*/listen.mode = 0660/' /etc/php/8.2/fpm/pool.d/www.conf

# Ensure PHP session directory is writable by asterisk
mkdir -p /var/lib/php/sessions
chown asterisk:asterisk /var/lib/php/sessions

# ---------------------------------------------------------------
# HylaFAX setup — ensure spool dir structure
# ---------------------------------------------------------------
mkdir -p /var/spool/hylafax/{recvq,sendq,doneq,archive,tmp,log,etc,bin,config}
if [ ! -f /var/spool/hylafax/etc/hosts.hfaxd ]; then
    echo "localhost" > /var/spool/hylafax/etc/hosts.hfaxd
    echo "127.0.0.1" >> /var/spool/hylafax/etc/hosts.hfaxd
fi

# Copy HylaFAX configs to spool if not present (or if broken symlinks)
for f in config config.ttyIAX0 setup.cache setup.modem; do
    target="/var/spool/hylafax/etc/$f"
    if [ ! -e "$target" ] && [ -f "/etc/hylafax/$f" ]; then
        cp "/etc/hylafax/$f" "$target"
    fi
done

chown -R uucp:uucp /var/spool/hylafax 2>/dev/null || true

# ---------------------------------------------------------------
# Cron: hourly WAV -> MP3 conversion
# ---------------------------------------------------------------
echo "0 * * * * /usr/local/bin/mp3.sh >> /var/log/asterisk/mp3.log 2>&1" | crontab -

# ---------------------------------------------------------------
# Start services via supervisord
# ---------------------------------------------------------------
echo "=== Starting supervisord ==="
exec "$@"

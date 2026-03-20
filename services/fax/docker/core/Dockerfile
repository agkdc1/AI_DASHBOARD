# =============================================================================
# RasPBX Core Container — Multi-Stage Build
# Asterisk 20.18.2 + FreePBX 17 + Nginx + PHP-FPM + iaxmodem + HylaFAX
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build Asterisk from source
# ---------------------------------------------------------------------------
FROM debian:bookworm AS asterisk-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV ASTERISK_VERSION=20.18.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make patch wget ca-certificates \
    libedit-dev libssl-dev libxml2-dev libsqlite3-dev uuid-dev \
    libsrtp2-dev libspandsp-dev libcurl4-openssl-dev libjansson-dev \
    libbluetooth-dev unixodbc-dev libncurses-dev libnewt-dev \
    libcap-dev libneon27-dev libgmime-3.0-dev liblua5.2-dev \
    libiksemel-dev libresample1-dev libspeex-dev libspeexdsp-dev \
    libtiff-dev libfftw3-dev freetds-dev libpq-dev libcorosync-common-dev \
    libcpg-dev libcfg-dev libsnmp-dev libical-dev \
    autoconf automake libtool pkg-config bison flex \
    python3 python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src

RUN wget -q "https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}.tar.gz" \
    && tar xzf "asterisk-${ASTERISK_VERSION}.tar.gz" \
    && rm "asterisk-${ASTERISK_VERSION}.tar.gz"

WORKDIR /usr/src/asterisk-${ASTERISK_VERSION}

# Build deps already installed above; skip install_prereq (needs aptitude)
RUN ./configure \
    --with-pjproject-bundled \
    --with-jansson-bundled \
    --with-crypto \
    --with-ssl \
    --with-srtp \
    --with-spandsp

# Generate default menuselect with dep auto-detection, then apply overrides
RUN make menuselect/cmenuselect menuselect/nmenuselect menuselect/gmenuselect menuselect/menuselect menuselect-tree

# Apply the same module selections as bare metal via CLI
# Disable modules we don't need (channels)
RUN menuselect/menuselect --disable chan_dahdi --disable chan_motif \
    --disable chan_console --disable chan_alsa --disable chan_mgcp \
    --disable chan_sip --disable chan_skinny menuselect.makeopts
# Disable codecs without deps
RUN menuselect/menuselect --disable codec_opus --disable codec_silk \
    --disable codec_g729a menuselect.makeopts
# Disable apps without deps
RUN menuselect/menuselect --disable app_meetme --disable app_osplookup \
    menuselect.makeopts
# Enable critical build deps
RUN menuselect/menuselect --enable res_fax --enable res_pjsip \
    --enable res_crypto --enable DONT_OPTIMIZE --enable G711_NEW_ALGORITHM \
    --enable BUILD_NATIVE --enable OPTIONAL_API menuselect.makeopts
# Enable sounds
RUN menuselect/menuselect --enable CORE-SOUNDS-EN-WAV --enable CORE-SOUNDS-EN-ULAW \
    --enable CORE-SOUNDS-EN-GSM --enable CORE-SOUNDS-EN-G722 \
    --enable MOH-OPSOUND-WAV \
    --enable EXTRA-SOUNDS-EN-WAV --enable EXTRA-SOUNDS-EN-ULAW \
    --enable EXTRA-SOUNDS-EN-GSM --enable EXTRA-SOUNDS-EN-G722 \
    menuselect.makeopts
RUN make -j$(nproc)
RUN make install
RUN make config
RUN make install-headers
RUN ldconfig

# ---------------------------------------------------------------------------
# Stage 2: Install FreePBX
# ---------------------------------------------------------------------------
FROM asterisk-builder AS freepbx-installer

ENV DEBIAN_FRONTEND=noninteractive
ENV FREEPBX_VERSION=17

# PHP 8.2 + extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    php8.2 php8.2-fpm php8.2-mysql php8.2-gd php8.2-curl php8.2-xml \
    php8.2-mbstring php8.2-zip php8.2-intl php8.2-bcmath php8.2-ldap \
    php8.2-cli php8.2-common php8.2-opcache php8.2-readline php8.2-imap \
    mariadb-client \
    nginx \
    git curl sudo cron \
    && rm -rf /var/lib/apt/lists/*

# Node.js (Debian stock 18.x) + npm + PM2
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g pm2 \
    && rm -rf /var/lib/apt/lists/*

# Create asterisk user
RUN groupadd -g 1000 asterisk || true \
    && useradd -u 1000 -g asterisk -d /var/lib/asterisk -s /bin/bash asterisk || true

# Set ownership for Asterisk
RUN chown -R asterisk:asterisk /var/run/asterisk /var/lib/asterisk \
    /var/log/asterisk /var/spool/asterisk /etc/asterisk \
    /usr/lib/asterisk 2>/dev/null || true

# Download FreePBX
RUN cd /usr/src \
    && wget -q "http://mirror.freepbx.org/modules/packages/freepbx/freepbx-${FREEPBX_VERSION}.0-latest.tgz" \
    && tar xzf "freepbx-${FREEPBX_VERSION}.0-latest.tgz" \
    && rm "freepbx-${FREEPBX_VERSION}.0-latest.tgz"

# FreePBX install is deferred to entrypoint (needs DB connection)
# But we prepare the web root
RUN mkdir -p /var/www/html \
    && chown -R asterisk:asterisk /var/www/html

# ---------------------------------------------------------------------------
# Stage 3: Runtime image
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV ASTERISK_VERSION=20.18.2
ENV PATH="/var/lib/asterisk/bin:${PATH}"

# Runtime packages (excluding HylaFAX — installed separately to handle prompts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PHP runtime
    php8.2-fpm php8.2-mysql php8.2-gd php8.2-curl php8.2-xml \
    php8.2-mbstring php8.2-zip php8.2-intl php8.2-bcmath php8.2-ldap \
    php8.2-cli php8.2-common php8.2-opcache php8.2-readline php8.2-imap \
    # Web server
    nginx \
    # Fax subsystem (iaxmodem only — hylafax below)
    iaxmodem \
    sox libtiff-tools \
    # Database client (for fwconsole)
    mariadb-client \
    # Process manager
    supervisor \
    # Utilities
    curl wget sudo cron git procps net-tools lame \
    # Runtime libraries for Asterisk
    libssl3 libxml2 libsqlite3-0 libedit2 libsrtp2-1 libspandsp2 \
    libuuid1 libjansson4 libbluetooth3 libcurl4 libodbc2 \
    libncurses6 libnewt0.52 libcap2 libneon27 libgmime-3.0-0 \
    libresample1 libtiff6 libfftw3-single3 libical3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# HylaFAX: faxsetup in postinst reads /dev/tty and can't be suppressed.
# Strategy: extract packages without running postinst, then fix up manually.
RUN apt-get update \
    && apt-get download hylafax-server hylafax-client \
    && dpkg --unpack hylafax-client_*.deb || true \
    && dpkg --unpack hylafax-server_*.deb || true \
    && rm -f /var/lib/dpkg/info/hylafax-server.postinst \
    && dpkg --configure hylafax-client || true \
    && dpkg --configure hylafax-server || true \
    && apt-get install -y --no-install-recommends -f \
    && rm -f hylafax-*.deb \
    && rm -rf /var/lib/apt/lists/*

# Node.js (Debian stock 18.x) + npm + PM2
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g pm2 \
    && rm -rf /var/lib/apt/lists/*

# Create users
RUN groupadd -g 1000 asterisk 2>/dev/null || true \
    && useradd -u 1000 -g asterisk -d /var/lib/asterisk -s /bin/bash asterisk 2>/dev/null || true

# Copy all Asterisk installed files from builder (avoids missing binary issues)
COPY --from=asterisk-builder /usr/sbin/asterisk /usr/sbin/
COPY --from=asterisk-builder /usr/sbin/safe_asterisk /usr/sbin/
COPY --from=asterisk-builder /usr/sbin/rasterisk /usr/sbin/
COPY --from=asterisk-builder /usr/lib/asterisk/ /usr/lib/asterisk/
COPY --from=asterisk-builder /usr/lib/libasterisk* /usr/lib/
COPY --from=asterisk-builder /var/lib/asterisk/ /var/lib/asterisk/
COPY --from=asterisk-builder /var/spool/asterisk/ /var/spool/asterisk/
COPY --from=asterisk-builder /etc/asterisk/ /etc/asterisk/

# Copy FreePBX source for install at first boot
COPY --from=freepbx-installer /usr/src/freepbx /usr/src/freepbx

# Create required directories
RUN mkdir -p /var/run/asterisk /var/log/asterisk /var/spool/asterisk/fax/outgoing \
    /var/spool/asterisk/fax/incoming /var/www/html \
    /run/php /var/log/php8.2-fpm \
    && chown -R asterisk:asterisk /var/run/asterisk /var/lib/asterisk \
    /var/log/asterisk /var/spool/asterisk /etc/asterisk \
    /var/www/html 2>/dev/null || true

# Refresh shared library cache
RUN ldconfig

# Copy configuration files
COPY supervisord.conf /etc/supervisor/conf.d/raspbx.conf
COPY nginx.conf /etc/nginx/sites-available/freepbx
COPY iaxmodem-ttyIAX0 /etc/iaxmodem/ttyIAX0
COPY hylafax/config /etc/hylafax/config
COPY hylafax/config.ttyIAX0 /etc/hylafax/config.ttyIAX0
COPY hylafax/setup.cache /etc/hylafax/setup.cache
COPY hylafax/setup.modem /etc/hylafax/setup.modem
COPY mp3.sh /usr/local/bin/mp3.sh
COPY entrypoint.sh /entrypoint.sh

# Nginx setup
RUN rm -f /etc/nginx/sites-enabled/default \
    && ln -sf /etc/nginx/sites-available/freepbx /etc/nginx/sites-enabled/freepbx

RUN chmod +x /entrypoint.sh

# Expose ports
EXPOSE 5060/udp 4569/udp 4570/udp 5038/tcp 9000/tcp 10000-20000/udp

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/raspbx.conf"]

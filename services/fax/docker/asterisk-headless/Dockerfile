# =============================================================================
# Headless Asterisk — Asterisk 20 + confgen (no FreePBX/PHP/MariaDB)
# =============================================================================
# Reuses the Asterisk build from the core Dockerfile, strips FreePBX.
# Config managed by SQLite + confgen.py via faxapi.

# ---------------------------------------------------------------------------
# Stage 1: Copy Asterisk from the core builder
# ---------------------------------------------------------------------------
FROM fax-core:latest AS core-source

# ---------------------------------------------------------------------------
# Stage 2: Minimal Asterisk runtime
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Asterisk runtime deps
    libedit2 libssl3 libxml2 libsqlite3-0 uuid-runtime \
    libsrtp2-1 libspandsp2 libcurl4 libjansson4 \
    libncurses6 libnewt0.52 libcap2 libneon27 \
    libgmime-3.0-0 liblua5.2-0 libresample1 \
    libspeex1 libspeexdsp1 libtiff6 libfftw3-single3 \
    libpq5 unixodbc libsnmp40 libical3 \
    # IAXmodem (fax bridge)
    iaxmodem \
    # Python for confgen (CLI testing only)
    python3 sqlite3 \
    # Utilities
    tzdata ca-certificates procps net-tools \
    && rm -rf /var/lib/apt/lists/*

# HylaFAX: faxsetup in postinst reads /dev/tty — bypass it
# (same trick as core Dockerfile)
RUN apt-get update \
    && apt-get download hylafax-server hylafax-client \
    && dpkg --unpack hylafax-client_*.deb || true \
    && dpkg --unpack hylafax-server_*.deb || true \
    && rm -f /var/lib/dpkg/info/hylafax-server.postinst \
    && dpkg --configure hylafax-client || true \
    && dpkg --configure hylafax-server || true \
    && apt-get install -f -y --no-install-recommends \
    && rm -f hylafax-*.deb \
    && rm -rf /var/lib/apt/lists/*

# Copy Asterisk binaries and libs from core image
COPY --from=core-source /usr/sbin/asterisk /usr/sbin/asterisk
COPY --from=core-source /usr/lib/libasteriskssl.so* /usr/lib/
COPY --from=core-source /usr/lib/libasteriskpj.so* /usr/lib/
COPY --from=core-source /usr/lib/asterisk/ /usr/lib/asterisk/
COPY --from=core-source /var/lib/asterisk/ /var/lib/asterisk/
RUN ldconfig

# Create asterisk user
RUN groupadd -g 1000 asterisk && \
    useradd -u 1000 -g asterisk -s /bin/false -d /var/lib/asterisk asterisk

# Create required directories
RUN mkdir -p /etc/asterisk /var/log/asterisk /var/run/asterisk \
    /var/spool/asterisk /var/spool/hylafax \
    && chown -R asterisk:asterisk /var/log/asterisk /var/run/asterisk /var/spool/asterisk

# Copy entrypoint
COPY docker/asterisk-headless/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 5060/udp
EXPOSE 5060/tcp
EXPOSE 8088

ENTRYPOINT ["/opt/entrypoint.sh"]

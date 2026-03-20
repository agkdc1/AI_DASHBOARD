FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        samba \
        samba-vfs-modules \
        winbind \
        libnss-winbind \
        libpam-winbind \
        krb5-user \
        supervisor \
        procps \
    && rm -rf /var/lib/apt/lists/*

COPY smb-shares.conf /etc/samba/smb-shares.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create share directories
RUN mkdir -p /srv/samba/profiles /srv/samba/shared

EXPOSE 445/tcp

ENTRYPOINT ["/entrypoint.sh"]

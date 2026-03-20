FROM google/cloud-sdk:slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client postgresql-client xz-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY backup.sh /backup.sh
RUN chmod +x /backup.sh

ENTRYPOINT ["/backup.sh"]

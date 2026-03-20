FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        libldap2-dev \
        libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        google-auth \
        google-api-python-client \
        python-ldap

COPY sync.py /app/sync.py
WORKDIR /app

CMD ["python", "sync.py"]

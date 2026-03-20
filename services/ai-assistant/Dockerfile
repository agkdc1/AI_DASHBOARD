FROM python:3.12-slim-bookworm

WORKDIR /app

# PaddleOCR deps + build tools for python-ldap
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    libldap-2.5-0 libsasl2-2 libsasl2-dev libldap-dev \
    gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8030

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]

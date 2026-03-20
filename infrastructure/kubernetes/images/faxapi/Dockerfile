FROM python:3.11-slim-bookworm

WORKDIR /app

COPY services/fax/docker/faxapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/fax/docker/faxapi/fax_api.py .
COPY services/fax/docker/faxapi/confgen.py .

ENV AMI_HOST=127.0.0.1
ENV AMI_PORT=5038
ENV FAX_API_PORT=8010
ENV PBX_DB_PATH=/var/lib/asterisk/pbx.db

EXPOSE 8010

CMD ["sh", "-c", "uvicorn fax_api:app --host 0.0.0.0 --port ${FAX_API_PORT}"]

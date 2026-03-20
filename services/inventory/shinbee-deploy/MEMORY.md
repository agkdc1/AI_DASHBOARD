# Shinbee InvenTree Deployment - Progress

## What Was Done

Created a complete Unix-socket-based Docker deployment for InvenTree via a single `deploy.sh` generator script, with HTTPS via Let's Encrypt (DNS-01 challenge) and Route53 dynamic DNS.

### Architecture

```
    Port 80 (→301 HTTPS)    Port 443 (TLS)
      |                        |
  +---+------------------------+---+
  |           Nginx                |  terminates TLS, serves static/media
  +---+------+-----+---+----------+
      |             |
      | uwsgi sock  | reads certs from
      |             | /etc/letsencrypt/live/$DOMAIN/
  +---+------+   +--+----------+
  | InvenTree|   |   Certbot   |  DNS-01 challenge via Route53
  | (+ Worker)   +--+----------+
  +---+------+      | writes certs to certbot-data volume
      | MySQL sock   | reads AWS creds from .aws/ mount
  +---+--+
  | MySQL|
  +------+
```

All inter-container communication uses Unix sockets (no TCP). MySQL password is managed via Docker secrets. TLS certificates are managed by a dedicated certbot container using Let's Encrypt DNS-01 challenge via Route53.

### Generated Files

| File | Purpose |
|---|---|
| `deploy.sh` (repo root) | Generator script - creates all files below via heredocs |
| `shinbee-deploy/docker-compose.yml` | 5 services: mysql, certbot, inventree-server, inventree-worker, nginx |
| `shinbee-deploy/Dockerfile` | Extends `inventree/inventree:stable`, adds uWSGI |
| `shinbee-deploy/Dockerfile.certbot` | Extends `certbot/dns-route53:latest`, adds curl/jq/bash + scripts |
| `shinbee-deploy/nginx.conf.template` | HTTPS reverse proxy with `envsubst` for domain injection |
| `shinbee-deploy/uwsgi.ini` | uWSGI config: 4 processes, 2 threads, 120s timeout |
| `shinbee-deploy/config.yaml` | Django DB config with `OPTIONS.unix_socket` |
| `shinbee-deploy/init-wrapper.sh` | Reads Docker secret, runs migrations (server only), then starts uWSGI or worker |
| `shinbee-deploy/certbot-entrypoint.sh` | Placeholder cert → mark ready → DNS update → real cert → renewal loop |
| `shinbee-deploy/route53-update.py` | Auto-detect hosted zone, UPSERT A record with public IP |
| `shinbee-deploy/reload-nginx.sh` | Send SIGHUP to nginx via Docker socket API |
| `shinbee-deploy/.env` | Image tag, domain, site URL, ports (no passwords) |
| `shinbee-deploy/secrets/mysql_password` | Auto-generated random password (gitignored) |

### Key Design Decisions

- **MySQL connection**: `HOST: ''` + `OPTIONS.unix_socket` in config.yaml. `INVENTREE_DB_HOST` env var intentionally omitted so settings.py doesn't override config.yaml's empty HOST.
- **Password flow**: Docker secret file -> `init-wrapper.sh` reads it -> exports `INVENTREE_DB_PASSWORD` env var -> settings.py picks it up. Password never in `.env` or `config.yaml`.
- **uWSGI replaces Gunicorn**: Installed via pip in Dockerfile (needs gcc/python3-dev for compilation, purged after).
- **Nginx media auth**: `/media/` uses `auth_request /auth` subrequest via `uwsgi_pass` (not proxy_pass).
- **Config provisioning**: `config.yaml` copied to `/home/inventree/config.yaml.default` in image; `init-wrapper.sh` copies it to `$INVENTREE_CONFIG_FILE` on first run.
- **Migrations**: `init-wrapper.sh` runs `invoke migrate` + `invoke static` only for the server (uWSGI) container. The worker skips these to avoid MySQL lock contention on simultaneous startup. The worker's `invoke worker` has its own built-in DB-wait logic.
- **HTTPS via DNS-01**: Certbot uses Route53 DNS-01 challenge. No HTTP challenge ports needed; works even if port 80 isn't publicly accessible yet.
- **Placeholder certificate**: On first boot, certbot creates a self-signed cert so nginx can start immediately with HTTPS. Replaced by real Let's Encrypt cert shortly after.
- **envsubst templates**: Uses stock nginx image's built-in template processing. `INVENTREE_DOMAIN` env var is substituted at container start; nginx variables (`$host`, `$request_uri`, etc.) are unaffected because only explicitly defined env vars are substituted.
- **Docker socket mount**: Required for certbot to reload nginx after renewal. Acceptable for self-hosted Raspberry Pi deployment.
- **Auto-detect hosted zone**: `route53-update.py` finds the Route53 zone ID from the domain name automatically (no manual Zone ID config needed).
- **Dynamic DNS (every 5 min)**: `route53-update.py` updates A record (and AAAA if IPv6 is available) every 5 minutes via a background loop. Two modes controlled by `DNS_MODE` env var: `production` uses external/public IPs, `test` uses internal/private IPv4 only (no AAAA).
- **Idempotent**: Re-running `deploy.sh` preserves existing password.

### Startup Sequence

1. **MySQL** starts, becomes healthy
2. **Certbot** starts → creates placeholder self-signed cert → marks `.ready` → becomes healthy → begins DNS update + real cert acquisition in background
3. **Nginx** starts (depends on certbot healthy) → loads placeholder cert → serves HTTPS immediately
4. **InvenTree server** starts (depends on MySQL healthy) → runs migrations → starts uWSGI
5. **InvenTree worker** starts (depends on server started)
6. Certbot finishes getting real cert → sends HUP to nginx → nginx reloads with real cert

### Verification Status

- [x] `deploy.sh` runs without errors
- [x] `docker compose config --quiet` validates compose file
- [x] Idempotency confirmed (re-run preserves password)
- [x] `docker compose build` - images build successfully (uWSGI compiled on aarch64)
- [x] `docker compose up -d` - all 5 containers start and stay healthy
- [x] End-to-end: `curl http://localhost/api/` - HTTP 200, InvenTree v1.1.11, worker_running=true
- [x] Let's Encrypt certificate obtained via DNS-01 (expires 2026-05-05)
- [x] HTTP→HTTPS redirect (301) working
- [x] HTTPS endpoint: `curl -k -H "Host: api.your-domain.com" https://localhost/api/` - HTTP 200
- [x] Certificate auto-renewal loop running (every 30 days)
- [ ] Route53 dynamic DNS - **blocked by IAM permissions** (see Known Issues)

### How to Deploy

```bash
# Generate deployment files (from repo root)
chmod +x deploy.sh && ./deploy.sh

# Build and start
cd shinbee-deploy
docker compose build
docker compose up -d

# Watch startup
docker compose logs -f inventree-certbot   # watch cert acquisition
docker compose logs -f inventree-server    # watch startup

# Test
curl -k https://localhost/api/             # self-signed (immediate)
curl https://api.your-domain.com/api/    # real cert (after certbot finishes)
```

### Known Issues

1. **Route53 dynamic DNS not working** — The IAM user `api.your-domain.com_ddns_manager` lacks `route53:ChangeResourceRecordSets` permission for A records. It can only create TXT records (for certbot DNS-01). To fix:
   - Add `route53:ChangeResourceRecordSets` to the IAM policy for A/AAAA record types
   - Delete the existing CNAME record for `api.your-domain.com` in Route53 (conflicts with A record creation)
   - The code handles CNAME conflicts automatically once permissions are granted

2. **Hosted zone auto-detection** — Changed from `list_hosted_zones_by_name` to `list_hosted_zones` (paginated) because the IAM user lacks the `ListHostedZonesByName` permission. Also added `ROUTE53_ZONE_ID` env var (set to `YOUR_ZONE_ID`) to skip auto-detection entirely.

3. **Placeholder cert cleanup** — certbot-entrypoint.sh now detects placeholder self-signed certs (no valid renewal config) and cleans them up before requesting real certs from Let's Encrypt.

### Prerequisites

- AWS credentials in `~/.aws/` (parent of shinbee-deploy) with Route53 permissions
- Route53 hosted zone for the domain (e.g., `your-domain.com`)
- Ports 80 and 443 open/forwarded to the host
- For dynamic DNS: IAM user needs `route53:ChangeResourceRecordSets` for A/AAAA records

### Source References

Key files in the InvenTree repo that informed the design:
- `src/backend/InvenTree/InvenTree/settings.py` (lines 620-824) - DB config, env var override logic
- `src/backend/InvenTree/InvenTree/wsgi.py` - WSGI module path
- `contrib/container/init.sh` - Original entrypoint behavior
- `contrib/container/Dockerfile` - Base image structure, env vars
- `contrib/container/gunicorn.conf.py` - Original WSGI server config (replaced by uWSGI)

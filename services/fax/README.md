# Shinbee Japan Fax

Part of the [SHINBEE](../README.md) monorepo. NTT Hikari Denwa voice/fax system running on a Raspberry Pi. Handles SIP calls via headless Asterisk with fax processing through HylaFAX and a GCP Cloud Function pipeline.

The PBX stack runs as Docker containers. FreePBX has been replaced by headless Asterisk with SQLite-backed config (`confgen.py`). Legacy FreePBX containers (raspbx-core, raspbx-db) are kept in docker-compose for rollback only.

**K8s migration note**: This stack stays on the Raspberry Pi and is NOT migrated to Kubernetes. NTT Hikari Denwa uses circuit-based SIP authentication (source IP from DHCP lease on eth1), which requires host networking on the physical interface. The core container uses `network_mode: host` for this reason. See `../../infrastructure/kubernetes/docs/ARCHITECTURE.md` for the full migration plan.

**Configuration**: Non-secret values come from the root `config.yaml`. Secrets are injected by `vault-render-fax.service` at boot. See the [parent README](../README.md) for the full deployment flow.

## System Architecture

```
                                   NTT NGN Network
                                        |
                                   +---------+
                                   | NTT ONU |
                                   +----+----+
                                        |
                                        |
                                   eth1 | 203.0.113.62
                                   eth0 | 10.0.x.x (LAN)
                                        |
                                  +-----+----------------+
                                  |   Raspberry Pi 5     |
                                  |                      |
  HOST:                           |   iptables firewall  |
                                  |                      |
                                  +----------+-----------+
                                             |
            +--------------------------------+--------------------------------+
            |                    Docker (production: host network)             |
            |                                                                 |
            |  +----------+  +------------------------------------------+     |
            |  | raspbx-  |  | raspbx-core                             |     |
            |  | db       |  |  Asterisk 20.18.2 (compiled from src)   |     |
            |  |          |  |  FreePBX 17 + Nginx + PHP-FPM           |     |
            |  | MariaDB  |<>|  iaxmodem 1.2.0 (PTY /dev/ttyIAX0)     |     |
            |  | 10.11    |  |  HylaFAX 6.0.7 (hfaxd + faxq + getty)  |     |
            |  | :3306    |  |  PM2/FastAGI (Node.js)                  |     |
            |  +----------+  |  supervisord (8 processes)              |     |
            |                +-------------------+---------------------+     |
            |                                    | AMI :5038                  |
            |                        +-----------+-----------+               |
            |                        | raspbx-faxapi         |               |
            |                        | FastAPI :8010          |               |
            |                        | (outbound fax via AMI) |               |
            |                        +-----------+-----------+               |
            |                                    | HTTP                       |
            |                        +-----------+-----------+               |
            |                        | raspbx-mail2fax       |               |
            |                        | Postfix :25            |               |
            |                        | (email -> fax gateway) |               |
            |                        +-----------------------+               |
            +-----------------------------------------------------------------+
                                             |
                                      +------+------+
                                      | GCP Cloud   |
                                      | Function    |
                                      | (OCR/Drive) |
                                      +-------------+
```

### Container Layout

| Container | Image | Purpose | Ports |
|-----------|-------|---------|-------|
| `raspbx-db` | `mariadb:10.11` | FreePBX database | 3306 |
| `raspbx-core` | Custom (multi-stage build) | Asterisk + FreePBX + Nginx + PHP-FPM + iaxmodem + HylaFAX | 5060/udp, 4569-4570/udp, 5038, 9000, 10000-20000/udp |
| `raspbx-faxapi` | Custom (python:3.11-slim) | Outbound fax REST API | 8010 |
| `raspbx-mail2fax` | Custom (Debian) | Email-to-fax gateway (Postfix) | 587 |

### Host-Level Components (Moved)

The following components have been moved to the parent repo under `system/`:
- **Windows client tools** (installer, PowerShell scripts) → `system/windows-client/`
- **MICROTIC.cmd** (router config) → `system/network/`

See the [parent README](../README.md) for details.

## Quick Start (Fresh System)

### Prerequisites

- Raspberry Pi 5 (aarch64, 4+ GB RAM) with Raspberry Pi OS Bookworm
- Two Ethernet interfaces (eth0 = LAN, eth1 = NTT NGN)
- Docker + Docker Compose installed
- Docker DNS fix: `/etc/docker/daemon.json` with `{"dns": ["8.8.8.8", "8.8.4.4"]}`

### 1. Clone and Configure

```bash
git clone <repo-url> SHINBEEHUB
cd SHINBEEHUB/services/fax

# Docker environment
cp .env.sample .env
nano .env  # Set all passwords
```

### 2. Migrate Bare-Metal Data (if existing system)

```bash
sudo ./scripts/migrate-data.sh
```

This exports MariaDB, Asterisk configs, FreePBX web root, HylaFAX spool, and voicemail into `./data/` bind mount directories. On a fresh system, skip this step - the container entrypoint will install FreePBX from scratch on first boot.

### 3. Build and Test (Quarantine Mode)

```bash
sudo docker compose build    # ~45-90 min (Asterisk compilation)
sudo docker compose up -d    # Internal-only network, no external access
```

Verify:
```bash
sudo docker exec raspbx-core asterisk -rx "core show version"
sudo docker exec raspbx-core asterisk -rx "module show" | tail -1
sudo docker exec raspbx-core fwconsole ma list | head -20
sudo docker logs raspbx-core 2>&1 | grep -E "(ERROR|started)"
```

### 4. Production Cutover

```bash
sudo ./scripts/cutover.sh
```

This stops bare-metal services and starts the production stack with `network_mode: host` for the core container (required for NTT SIP source-IP authentication and RTP media).

### 5. Rollback (if needed)

```bash
sudo ./scripts/rollback.sh
```

## Directory Structure

```
services/fax/
├── docker-compose.yml              # Main compose (quarantine: internal network)
├── docker-compose.production.yml   # Production override (host network)
├── .env.sample                     # Environment template
│
├── docker/
│   ├── core/
│   │   ├── Dockerfile              # Multi-stage: asterisk-builder -> freepbx-installer -> runtime
│   │   ├── entrypoint.sh           # DB wait, FreePBX first-run install, HylaFAX setup
│   │   ├── supervisord.conf        # 8 processes: asterisk, php-fpm, nginx, iaxmodem, hfaxd, faxq, faxgetty, pm2
│   │   ├── nginx.conf              # FreePBX reverse proxy (port 9000)
│   │   ├── menuselect.makeopts     # Asterisk module selection
│   │   ├── iaxmodem-ttyIAX0        # iaxmodem config (IAX2 peer [800], port 4570)
│   │   └── hylafax/                # HylaFAX configs (config, config.ttyIAX0, setup.cache, setup.modem)
│   ├── db/
│   │   ├── custom.cnf              # MariaDB tuning (innodb_buffer_pool_size=256M)
│   │   └── init/                   # SQL dump for first-run import (gitignored, created by migrate-data.sh)
│   └── faxapi/
│       ├── Dockerfile              # Python 3.11-slim + FastAPI
│       ├── fax_api.py              # /send_fax endpoint (AMI Originate)
│       └── requirements.txt
│
├── mail2fax/                       # Email-to-fax gateway
│   ├── Dockerfile
│   ├── docker-compose.yml          # Standalone compose (for independent operation)
│   ├── entrypoint.sh
│   ├── config.yaml.sample
│   ├── config/                     # Postfix templates
│   └── scripts/                    # email_processor.py, dns_updater.py, cert_renewer.sh
│
├── src/                            # GCP Cloud Function (fax OCR pipeline)
│   ├── main.py                     # Gemini 2.0 Flash OCR -> Google Drive -> email notification
│   └── requirements.txt
│
├── scripts/
│   ├── migrate-data.sh             # Export bare-metal data to bind mounts
│   ├── cutover.sh                  # Stop bare metal, start Docker production
│   └── rollback.sh                 # Reverse cutover
│
├── main.tf                         # Terraform: GCP Cloud Function, Storage, IAM
├── variables.tf
└── mp3.sh                          # Utility script
```

## NTT-Specific Gotchas

These are critical for anyone modifying SIP/PJSIP configuration:

- **NTT does NOT use SIP REGISTER.** Authentication is circuit-based (source IP from DHCP lease). Never generate registration sections.
- **DID is in the SIP To header, not the Request-URI.** The `[from-ntt]` dialplan uses `PJSIP_HEADER(read,To)` to extract it.
- **One PJSIP endpoint per source IP.** NTT uses the same IP for voice and fax. Route by DID in the dialplan, not separate endpoints.
- **No User-Agent header.** The original OG810Xi doesn't send one. Set `user_agent=` (empty) in pjsip.conf `[global]`.
- **FreePBX overwrites pjsip.conf** on every `fwconsole restart`. The user_agent suppression must be re-patched after any restart.
- **NTT /30 subnet must be in transport local_net.** Otherwise PJSIP uses the external (internet) IP in the Via header, and NTT rejects with 404.
- **FreePBX localnets** in `kvstore_Sipsettings` is a JSON array of `{"net":"...","mask":"..."}` objects.
- **Never add a default route on eth1.** Rogue defaults on eth1 cause an internet blackhole.
- **Asterisk ACL order**: Last matching rule wins. `deny=0.0.0.0/0` must come BEFORE permit lines.

## Docker Build Notes and Pitfalls

### Asterisk Compilation (~45-90 min on Pi)

The `raspbx-core` Dockerfile uses a 3-stage build:
1. **asterisk-builder** - Compiles Asterisk 20.18.2 from source with `--with-pjproject-bundled --with-jansson-bundled --with-spandsp`
2. **freepbx-installer** - Downloads FreePBX 17, prepares for first-boot install
3. **runtime** - Debian bookworm-slim with only runtime libraries

Key lesson: **Do NOT use `menuselect --disable-all`** to disable test modules. In Asterisk's menuselect, `--disable-all` disables ALL modules across ALL categories, not just the category you're targeting. Instead, disable specific unwanted modules individually.

### HylaFAX in Docker

HylaFAX's `postinst` script calls `faxsetup` which reads `/dev/tty` interactively. This fails in Docker builds. The workaround is:
```dockerfile
RUN apt-get download hylafax-server hylafax-client \
    && dpkg --unpack hylafax-client_*.deb || true \
    && dpkg --unpack hylafax-server_*.deb || true \
    && rm -f /var/lib/dpkg/info/hylafax-server.postinst \
    && dpkg --configure hylafax-client || true \
    && dpkg --configure hylafax-server || true \
    && apt-get install -y -f
```

You must also provide `setup.cache` and `setup.modem` from a working bare-metal system, as `faxsetup` was never run.

### iaxmodem PTY

iaxmodem creates a pseudo-terminal (`/dev/ttyIAX0 -> /dev/pts/X`). HylaFAX's `faxgetty` opens this PTY directly. They MUST be in the same container (shared PTS namespace). iaxmodem also connects to Asterisk on `localhost:4570` (IAX2), requiring shared network namespace.

The container needs `cap_add: SYS_PTRACE` for PTY access.

### Production Network Mode

`network_mode: host` is mandatory for `raspbx-core` in production because:
- RTP range 10000-20000 = 10,001 Docker proxy processes (terrible for real-time audio)
- NTT circuit-based SIP auth requires exact source IP (Docker NAT breaks this)
- Asterisk needs both eth0 and eth1 interfaces

In host network mode, the core container talks to MariaDB via `127.0.0.1:3306` (published port) instead of Docker DNS.

### Docker DNS on Raspberry Pi

Docker DNS resolution doesn't work by default on this Pi. Required fixes:
- `/etc/docker/daemon.json`: `{"dns": ["8.8.8.8", "8.8.4.4"]}`
- `dns: [8.8.8.8, 8.8.4.4]` in each docker-compose service
- `sudo systemctl restart docker` after changing daemon.json

### FreePBX First-Boot Install

The entrypoint script creates `/etc/freepbx.conf` dynamically from environment variables and runs `fwconsole` to install FreePBX if `/var/www/html/admin/bootstrap.php` doesn't exist. On a migrated system (with data from `migrate-data.sh`), FreePBX is already installed and only `fwconsole chown` runs.

### PM2 Permission Issue

PM2 defaults to `PM2_HOME=/root/.pm2`. When supervisord runs pm2 as the `asterisk` user, it fails with EACCES. Fix: set `PM2_HOME="/var/lib/asterisk/.pm2"` in the supervisord environment.

### Healthcheck Without curl

The `python:3.11-slim` image doesn't include curl. Use Python stdlib for healthchecks:
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')"]
```

## Fax Pipeline

### Inbound (NTT -> HylaFAX -> GCP)

```
NTT SIP INVITE (To: 0312345679) -> [from-ntt] dialplan -> fax-iax context
  -> IAX2/800 -> iaxmodem (PTY ttyIAX0) -> HylaFAX faxgetty -> recvq/
  -> FaxDispatch -> GCP Cloud Storage -> Cloud Function (Gemini OCR)
  -> Google Drive + email notification
```

### Outbound (API -> Asterisk -> NTT)

```
POST /send_fax (PDF + number) -> raspbx-faxapi
  -> AMI Originate (PJSIP/ntt-trunk) -> [fax-outbound] context
  -> SendFAX() -> NTT SIP INVITE
```

### Outbound via Email (mail2fax)

```
Email (PDF attachment) to DID@fax.your-domain.com
  -> Postfix virtual transport -> email_processor.py
  -> HTTP POST to raspbx-faxapi /send_fax
  -> (same as outbound above)
```

## SMTP Authentication (mail2fax)

The mail2fax container requires SASL authentication for SMTP submissions. Connections are also restricted to `mynetworks` (LAN + Docker) at the client level, so WAN clients are rejected before auth is even attempted.

### How it works

- **SASL mechanism**: Cyrus SASL with `sasldb2` (auxprop) — no PAM/saslauthd needed
- **Client restrictions**: `smtpd_client_restrictions = permit_mynetworks, reject` blocks all non-LAN connections
- **Recipient restrictions**: LAN clients are permitted; authenticated clients are permitted; everything else is rejected

### Credentials

Credentials are stored in Vault at `secret/shinbee_japan_fax/smtp` (fields: `username`, `password`). To generate and store them:

```bash
# Generate random credentials
SMTP_USER="faxprinter"
SMTP_PASS=$(openssl rand -base64 32)

# Store in Vault
vault kv patch secret/shinbee_japan_fax/smtp username="$SMTP_USER" password="$SMTP_PASS"

# Re-render configs
sudo /home/pi/SHINBEE/Vault/scripts/render-fax-env.sh
```

After rendering, a `.smtp-credentials` file is written to the project directory (mode 0600). Read it to configure the printer, then delete it:

```bash
cat /home/pi/SHINBEE/services/fax/.smtp-credentials
# Configure printer, then:
rm /home/pi/SHINBEE/services/fax/.smtp-credentials
```

### Printer SMTP Settings

| Setting | Value |
|---------|-------|
| Server | `fax.your-domain.com` |
| Port | `587` |
| Auth | `LOGIN` |
| Username | (from `/root/faxcreds`) |
| Password | (from `/root/faxcreds`) |
| TLS | STARTTLS (required) |

### Verification

```bash
# Should reject (no auth):
swaks --to test@fax --server localhost --port 587 --tls

# Should accept (with auth):
swaks --to test@fax --server localhost --port 587 --tls \
  --auth LOGIN --auth-user USERNAME --auth-password PASSWORD
```

## GCP Components (Terraform)

`main.tf` provisions:
- Cloud Storage buckets (incoming fax, archive, function source)
- Cloud Function Gen2 (triggered by GCS upload, runs Gemini 2.0 Flash OCR)
- IAM bindings (service account, EventArc)
- The Cloud Function code is in `src/main.py`

## Verification Commands

```bash
# Container status
sudo docker ps --format "table {{.Names}}\t{{.Status}}"

# Asterisk
sudo docker exec raspbx-core asterisk -rx "core show version"
sudo docker exec raspbx-core asterisk -rx "pjsip show endpoint ntt-trunk"
sudo docker exec raspbx-core asterisk -rx "pjsip show channels"
sudo docker exec raspbx-core asterisk -rx "dialplan show from-ntt"
sudo docker exec raspbx-core asterisk -rx "iax2 show peers"

# FreePBX
sudo docker exec raspbx-core fwconsole ma list

# Fax API
curl -s http://localhost:8010/health

# HylaFAX
sudo docker exec raspbx-core faxstat -s

# Firewall
sudo iptables -L INPUT -n --line-numbers
```

## Network Details

| Item | Value |
|------|-------|
| NTT Assigned IP | 203.0.113.62/30 |
| NTT Gateway | 203.0.113.61 |
| NTT SIP Server | 203.0.113.1 (DHCP Option 120) |
| Voice DID | 0312345678 |
| Fax DID | 0312345679 |
| SIP Domain | ntt-east.ne.jp |
| mail2fax Domain | fax.your-domain.com |

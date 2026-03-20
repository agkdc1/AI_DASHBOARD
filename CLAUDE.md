# CLAUDE.md

This file provides guidance for Claude Code when working on the Shinbee Hub project.

## Project Overview

Shinbee Hub is the IT infrastructure for a small Japanese trading company. It's a hybrid cloud/edge system combining a K3s cluster on recycled laptops, a Raspberry Pi at the network edge, and GCP cloud services. The repo contains 6 backend services, a Flutter dashboard, and all deployment infrastructure.

## Repository Structure

```
services/              Backend microservices
  ai-assistant/          FastAPI — AI workplace assistant with PII masking (port 8030)
  fax/                   Asterisk + HylaFAX + mail2fax on Raspberry Pi (port 8010)
  inventory/             InvenTree plugins + deployment configs
  selenium-daemon/       FastAPI — browser automation for carrier portals (port 8020)
  rakuten-renewal/       Automated Rakuten API key renewal (scheduled CLI)
  phone-provisioning/    VoIP phone XML config generator

apps/                  Frontend applications
  dashboard/             Flutter (web + Android) — unified dashboard
  chrome-extension/      Chrome Manifest v3 — AI-guided web navigation

infrastructure/        Cluster and cloud configuration
  kubernetes/
    manifests/           K8s YAML organized by service
    terraform/           GCP + AWS infrastructure (Terraform >= 1.5)
    scripts/             Cluster bootstrap, migration, secret rendering
    images/              Dockerfiles for K8s container builds

scripts/               Top-level operational scripts
  install.sh             Phased deployment (17 phases)
  backup.sh              Encrypted backup to GCS
  restore.sh             Restore from GCS
  render-secrets.sh      Pull secrets from GCP Secret Manager → .env files

docs/                  Presentations and setup guides
```

## Tech Stack

- **Python 3.12** — AI assistant, selenium daemon, rakuten renewal
- **Python 3.11** — FAX API
- **Dart 3.8.1 / Flutter** — Dashboard (web + mobile)
- **JavaScript** — Chrome extension
- **Terraform >= 1.5** — GCP (google ~> 5.0), AWS (aws ~> 5.0)
- **K3s** — Kubernetes on recycled laptops + GCP e2-micro control plane
- **Docker Compose** — FAX stack on Raspberry Pi

## Configuration

All non-secret configuration lives in `config.yaml` (copy from `config.yaml.example`). Shell scripts read it via a `cfg()` helper that uses `python3 + pyyaml`:

```bash
cfg() {
  python3 -c "
import yaml,sys,functools
with open('${CONFIG_FILE}') as f: c=yaml.safe_load(f)
keys=sys.argv[1].split('.')
v=functools.reduce(lambda d,k: d[int(k)] if isinstance(d,list) else d[k], keys, c)
print(v)
" "$1"
}
```

All secrets live in **GCP Secret Manager**. Run `scripts/render-secrets.sh` to generate `.env` files. See `docs/secrets-setup.md` for the full secret inventory.

## Building and Testing

### Python services (ai-assistant, selenium-daemon, rakuten-renewal)

```bash
# Install dependencies
pip install -r services/ai-assistant/requirements.txt

# Run tests (ai-assistant has the most comprehensive test suite)
pytest services/ai-assistant/tests/
pytest services/ai-assistant/tests/ -m "not integration"   # skip live service tests
pytest services/ai-assistant/tests/ -m "not slow"           # skip Gemini calls

# Prompt quality tests (requires RUN_PROMPT_TESTS=1)
RUN_PROMPT_TESTS=1 pytest services/ai-assistant/tests/ -m prompt_test
```

Test markers defined in `services/ai-assistant/pytest.ini`:
- `integration` — requires live production services
- `slow` — live Gemini API calls
- `prompt_test` — prompt quality evaluation (gated by env var)
- `tts` — GCP Text-to-Speech tests

### Flutter dashboard

```bash
cd apps/dashboard
flutter pub get
flutter analyze              # lint check
flutter test                 # unit/widget tests
flutter build web            # production web build
flutter build apk            # Android build
```

Linting rules are in `apps/dashboard/analysis_options.yaml` (uses `flutter_lints`). Key rules: `prefer_const_constructors`, `avoid_print`, `prefer_single_quotes`.

Localization: Japanese (ja), Korean (ko), English (en) via `flutter_localizations` + ARB files.

### Docker images for K8s

```bash
# Build via Cloud Build (see infrastructure/kubernetes/scripts/cloud-build.sh)
# Images are pushed to GCP Artifact Registry (amd64 architecture)
```

### Terraform

```bash
cd infrastructure/kubernetes/terraform/gcp
terraform init
terraform plan
terraform apply
```

State stored in GCS bucket. Backend configured in each `main.tf`.

## Kubernetes

Four namespaces:
- `shinbee` — main production (InvenTree, selenium, rakuten, Flutter, AI assistant)
- `intranet` — wiki + tasks (Outline, Vikunja, PostgreSQL, Redis, MinIO)
- `fax-system` — VoIP/FAX stack (Asterisk, mail2fax, faxapi)
- `shinbee-test` — E2E testing

Priority classes: `shinbee-critical` (1000), `shinbee-high` (500), `shinbee-normal` (100).

Manifests are in `infrastructure/kubernetes/manifests/`, organized by service subdirectory.

## Service Dependencies

```
Flutter Dashboard
  ├→ AI Assistant → Gemini, GCS, LDAP, Vikunja API
  ├→ InvenTree API → MySQL, marketplace plugins
  ├→ Vikunja → PostgreSQL, Redis
  └→ Outline → PostgreSQL, MinIO

Selenium Daemon → Chromium sessions (Yamato, Sagawa, Rakuten) → Gemini, GCS, Firestore
Rakuten Renewal → Chromium (nodriver) → Firestore (2FA polling), GCS, Gemini
FAX System → Asterisk → NTT SIP trunk, HylaFAX → Cloud Function (OCR) → Google Drive
Phone Provisioning → Grandstream phones → WiFi (Omada), LDAP, PBX SIP
```

## Key Conventions

- **No secrets in code.** All secrets come from GCP Secret Manager via `render-secrets.sh`. The repo tracks only `config.yaml.example` — never `config.yaml`.
- **Single config file.** `config.yaml` is the source of truth for all non-secret values. Services read from it at startup or via rendered `.env` files.
- **Phased deployment.** `scripts/install.sh` supports `--phase <name>` for incremental deployment. Run `scripts/install.sh --help` for the phase list.
- **Hybrid deployment.** FAX stack runs as Docker Compose on the Raspberry Pi (requires physical NTT SIP interface). Everything else runs on the K3s cluster.
- **Recycled hardware.** K3s workers are old laptops connected via WiFi + Tailscale VPN. No static LAN IPs required.
- **PII masking.** The AI assistant masks all PII before sending data to Gemini. Raw data goes to a GCS bucket with 7-day lifecycle. All LLM input is sanitized.

## File Patterns

- Service entry points: `main.py` (Python), `main.dart` (Flutter)
- FastAPI routers: `<module>/router.py` with service logic in `<module>/service.py`
- Config loading: `config.py` in each Python service (Pydantic Settings)
- Tests: `tests/` directory with `conftest.py` fixtures
- K8s manifests: `infrastructure/kubernetes/manifests/<service>/` with deployment, service, configmap, ingress YAML
- Terraform: `infrastructure/kubernetes/terraform/{gcp,aws}/` and per-service `terraform/` directories
- Docker: `Dockerfile` at service root, `docker-compose.yml` for local/edge deployment

## Things to Avoid

- Never commit `config.yaml`, `.env` files, or any credentials
- Never hardcode IPs, domains, or personal information — use config.yaml values
- The `system/ngn-handoff` and MAC cloning features have been removed — do not reference them
- Vault is decommissioned — secrets use GCP Secret Manager exclusively
- Don't modify Terraform resource names (causes destroy/recreate)
- Don't change Vault KV paths in seed scripts (they reference external store paths, not filesystem)

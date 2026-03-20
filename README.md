# Shinbee Hub

**What happens when you over-engineer your family business's IT infrastructure (and don't regret it one bit).**

## The Story

Shinbee Japan is a small Japanese trading company — the kind where the boss has been doing things the same way for decades, and it works. Orders came in by fax. Inventory lived in handwritten ledgers and Excel spreadsheets passed around on USB sticks. The office was a jungle of RJ11 phone cables and RJ45 Ethernet cables stapled to walls and taped across floors. If someone tripped over the right cable, the fax machine went down and so did half the day's orders.

We changed all of that. The cables came off the walls and got replaced with enterprise-provisioned WiFi. The handwritten ledgers and Excel files became an integrated inventory management system connected to every Japanese marketplace the company sells on — Rakuten, Amazon JP, Yahoo Shopping, Qoo10. The fax machine? Still works, but now it's VoIP running on a Raspberry Pi. Orders that used to take a phone call, a fax, and a prayer now go through a unified Flutter dashboard with one-click waybill printing. We even built an AI assistant that helps employees navigate their daily tasks — with PII masking, because we take privacy seriously even when we're a ten-person shop.

The whole thing runs on a Kubernetes cluster built from recycled laptops, a Raspberry Pi at the network edge, and a micro GCP instance as the control plane. Is it over-engineered for a small family business? Absolutely. Does it work beautifully? Also absolutely.

## What's Inside

```
services/          Backend services
  fax/               VoIP/Fax gateway (Asterisk + HylaFAX on Raspberry Pi)
  inventory/         Inventory management (InvenTree + marketplace integrations)
  ai-assistant/      AI-powered workplace assistant with PII masking
  selenium-daemon/   Browser automation for carrier portals and marketplace tasks
  rakuten-renewal/   Automated Rakuten API key renewal (yes, this needs its own service)
  phone-provisioning/  VoIP phone auto-configuration

apps/              Frontend applications
  dashboard/         Flutter unified dashboard (web + mobile)
  chrome-extension/  AI-guided web navigation helper

infrastructure/    Deployment and cluster configuration
  kubernetes/        K3s manifests, Helm values, Terraform (GCP + AWS)

scripts/           Deployment, backup, and secret rendering
docs/              Presentations and setup guides
```

## Architecture

```
                           ┌─────────────────────┐
                           │   GCP (Cloud)        │
                           │  ┌───────────────┐   │
                           │  │ Secret Manager │   │
                           │  │ Cloud DNS      │   │
                           │  │ GCS Buckets    │   │
                           │  │ Gemini AI      │   │
                           │  │ Firestore      │   │
                           │  │ Cloud Build    │   │
                           │  └───────────────┘   │
                           │  ┌───────────────┐   │
                           │  │ K3s Control    │   │
                           │  │ Plane (e2-micro)│  │
                           │  └───────┬───────┘   │
                           └──────────┼───────────┘
                              Tailscale VPN
                           ┌──────────┼───────────┐
                           │  Office  │  Network   │
        ┌──────────┐       │  ┌───────┴───────┐   │
        │ Flutter   │◄─────┼──┤ K3s Workers   │   │
        │ Dashboard │      │  │ (recycled     │   │
        │ (Web/App) │      │  │  laptops)     │   │
        └──────────┘       │  └───────────────┘   │
                           │                       │
   ┌──────────┐            │  ┌───────────────┐   │
   │ NTT PSTN │◄───────────┼──┤ Raspberry Pi  │   │
   │ (Fax/Tel)│            │  │  Fax Gateway  │   │
   └──────────┘            │  │  Proxy/Edge   │   │
                           │  └───────────────┘   │
                           │                       │
                           │  ┌───────────────┐   │
                           │  │ Enterprise    │   │
                           │  │ WiFi (Omada)  │   │
                           │  └───────────────┘   │
                           └───────────────────────┘
```

## Key Features

- **VoIP/Fax over IP** — Asterisk + HylaFAX + IAXmodem on a Raspberry Pi, replacing legacy NTT phone lines with SIP trunking. Incoming faxes get OCR'd and delivered to Google Drive.
- **Inventory management** — InvenTree integrated with Japanese marketplaces (Rakuten, Amazon JP, Yahoo Shopping, Qoo10) for unified stock tracking.
- **One-click waybill printing** — Automated shipping label generation for Yamato Transport and Sagawa Express through browser automation.
- **Automated Rakuten API key renewal** — Because Rakuten expires API keys every 90 days and the renewal portal has CAPTCHAs. Gemini solves them.
- **Internal wiki and task management** — Outline (wiki) + Vikunja (tasks) with SSO via Authentik, replacing sticky notes and group chat.
- **AI-powered assistant** — Gemini-based workplace assistant with PII masking that handles fax review, call requests, meeting scheduling, seating charts, and task management. Built to preserve existing work habits, not replace them.
- **Flutter dashboard** — Single app (web + Android) unifying inventory, fax, phone, tasks, and AI assistant under one sign-on. Localized in Japanese, Korean, and English.
- **Chrome extension** — AI-guided web navigation for marketplace and carrier portal tasks.
- **Enterprise WiFi** — Omada controller with provisioned access, replacing the cable spaghetti.
- **Kubernetes on recycled hardware** — K3s cluster running on old laptops as worker nodes, GCP e2-micro as control plane, connected via Tailscale.
- **Samba AD + LDAP** — Centralized identity for WiFi, phone provisioning, and application SSO.

## Tech Stack

| Layer | Tech |
|-------|------|
| **Frontend** | Flutter (Dart), Chrome Extension (JS) |
| **Backend** | Python (FastAPI), Shell scripts |
| **AI** | Google Gemini (Pro + Flash) |
| **Telephony** | Asterisk PBX, HylaFAX, IAXmodem, Grandstream GXP-1760W |
| **Inventory** | InvenTree |
| **Wiki/Tasks** | Outline, Vikunja |
| **Auth** | Authentik (OIDC/SSO), Samba AD, OpenLDAP |
| **Orchestration** | K3s, Docker Compose |
| **Infrastructure** | Terraform (GCP + AWS), cert-manager, MetalLB, Ingress-NGINX |
| **Cloud** | GCP (Secret Manager, GCS, Cloud DNS, Firestore, Cloud Build), AWS (Route53) |
| **Networking** | Tailscale (VPN), TP-Link Omada (WiFi), MikroTik (switching) |
| **Hardware** | Raspberry Pi 4, recycled laptops, GCP e2-micro |

## Getting Started

1. Copy and fill in the config:
   ```bash
   cp config.yaml.example config.yaml
   ```

2. Set up GCP Secret Manager access — see [`docs/secrets-setup.md`](docs/secrets-setup.md) for the full walkthrough (WIF with X.509 mTLS or service account key).

3. Render secrets and deploy:
   ```bash
   ./scripts/render-secrets.sh
   ./scripts/install.sh
   ```

## A Note on Secrets

Every secret in this project lives in GCP Secret Manager. No `.env` files are committed, no passwords in config files. You need exactly one credential to bootstrap everything — either a WIF X.509 certificate (recommended) or a GCP service account key. The `render-secrets.sh` script pulls secrets from GCP and generates all the `.env` files, Docker secrets, and Kubernetes secrets each service needs. See [`docs/secrets-setup.md`](docs/secrets-setup.md) for details.

## License

This repository is shared for **educational and reference purposes**. It documents a real-world small business IT transformation and may be useful if you're attempting something similar. The code is specific to our setup, but the patterns — hybrid cloud on recycled hardware, VoIP migration, marketplace integration, AI assistants with privacy guardrails — are broadly applicable.

Feel free to learn from it, borrow ideas, and adapt what's useful. If you're running a small business and thinking "this is way too much" — you're probably right, but it's also way too much fun to stop.

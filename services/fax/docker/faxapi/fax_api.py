"""FastAPI service for fax, NTT DHCP, PBX management via Asterisk AMI.

Containerized — uses environment variables for all configuration.

Env vars (fax):
    AMI_HOST     - Asterisk AMI host (default: core)
    AMI_PORT     - Asterisk AMI port (default: 5038)
    AMI_USERNAME - AMI login username
    AMI_SECRET   - AMI login secret
    FAX_API_KEY  - API key for authentication
    SIP_FROM_USER - CallerID number (default: 0312345678)

Env vars (NTT DHCP):
    NTT_SIP_SERVER      - NTT SIP server IP (default: 203.0.113.1)
    NTT_SIP_DOMAIN      - SIP From domain (default: ntt-east.ne.jp)
    NTT_VOICE_DID       - Voice DID (default: 0312345678)
    SIP_TRANSPORT        - PJSIP transport name (default: 0.0.0.0-udp)
    SIP_ALLOW            - SIP Allow header methods
    SIP_SUPPORTED        - SIP Supported header
    NTT_ALLOWED_SOURCES  - Comma-separated CIDRs for source IP check (default: 10.0.0.0/23)

Env vars (PBX):
    PBX_DB_PATH  - SQLite DB path (default: /var/lib/asterisk/pbx.db)

Env vars (Phone):
    PHONE_ADMIN_PASSWORD - Grandstream phone admin password

Env vars (OG810Xi):
    OG810XI_URL      - OG810Xi web GUI URL (default: http://192.168.1.1)
    OG810XI_USERNAME - Basic auth username (default: user)
    OG810XI_PASSWORD - Basic auth password (default: user)

Env vars (FreePBX DB — legacy, used during parallel operation):
    DB_HOST        - MariaDB host (default: db)
    DB_PORT        - MariaDB port (default: 3306)
    MYSQL_USER     - DB username
    MYSQL_PASSWORD - DB password
    MYSQL_DATABASE - DB name
"""

import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pymysql
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.security import APIKeyHeader

from confgen import ConfGen

log = logging.getLogger("fax_api")

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
AMI_HOST = os.environ.get("AMI_HOST", "core")
AMI_PORT = int(os.environ.get("AMI_PORT", "5038"))
AMI_USERNAME = os.environ.get("AMI_USERNAME", "")
AMI_SECRET = os.environ.get("AMI_SECRET", "")
FAX_API_KEY = os.environ.get("FAX_API_KEY", "")
SIP_FROM_USER = os.environ.get("SIP_FROM_USER", "0312345678")

# PBX SQLite config
PBX_DB_PATH = os.environ.get("PBX_DB_PATH", "/var/lib/asterisk/pbx.db")

# Phone config
PHONE_ADMIN_PASSWORD = os.environ.get("PHONE_ADMIN_PASSWORD", "")

# OG810Xi config
OG810XI_URL = os.environ.get("OG810XI_URL", "http://192.168.1.1")
OG810XI_USERNAME = os.environ.get("OG810XI_USERNAME", "user")
OG810XI_PASSWORD = os.environ.get("OG810XI_PASSWORD", "user")
OG810XI_SIP_USER = os.environ.get("OG810XI_SIP_USER", "10")
OG810XI_SIP_USER_FAX = os.environ.get("OG810XI_SIP_USER_FAX", "11")  # fax line (0312345679)
OG810XI_BIND_IP = os.environ.get("OG810XI_BIND_IP", "")  # auto-detect from OG810Xi subnet
OG810XI_FAX_BIND_IP = os.environ.get("OG810XI_FAX_BIND_IP", "192.168.1.103")  # macvlan for fax registration
OG810XI_GW_IP = os.environ.get("OG810XI_GW_IP", "192.168.1.1")
NTT_MODE = os.environ.get("NTT_MODE", "og810xi")  # "og810xi" (direct) or "nat" (MikroTik)

# NTT DHCP config
NTT_SIP_SERVER = os.environ.get("NTT_SIP_SERVER", "203.0.113.1")
NTT_SIP_DOMAIN = os.environ.get("NTT_SIP_DOMAIN", "ntt-east.ne.jp")
NTT_VOICE_DID = os.environ.get("NTT_VOICE_DID", "0312345678")
SIP_TRANSPORT = os.environ.get("SIP_TRANSPORT", "0.0.0.0-udp")
SIP_ALLOW = os.environ.get("SIP_ALLOW", "INVITE,ACK,BYE,CANCEL,PRACK,UPDATE,MESSAGE")
SIP_SUPPORTED = os.environ.get("SIP_SUPPORTED", "path,100rel,timer")

# FreePBX DB
DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "asterisk")

# Source IP restriction for NTT DHCP endpoint
NTT_ALLOWED_SOURCES = os.environ.get("NTT_ALLOWED_SOURCES", "10.0.0.0/23")
_allowed_networks = [
    ipaddress.IPv4Network(cidr.strip(), strict=False)
    for cidr in NTT_ALLOWED_SOURCES.split(",")
    if cidr.strip()
]


@asynccontextmanager
async def lifespan(application: FastAPI):
    log.info("Fax API started — AMI host=%s port=%d mode=%s", AMI_HOST, AMI_PORT, NTT_MODE)
    # Generate NTT trunk config on startup
    if NTT_MODE == "og810xi":
        bind_ip = _detect_bind_ip(OG810XI_GW_IP)
        if bind_ip:
            if _generate_pjsip_ntt_dynamic_og810xi(bind_ip, OG810XI_GW_IP, OG810XI_SIP_USER):
                log.info("OG810Xi trunk config written on startup (bind=%s)", bind_ip)
        else:
            log.warning("Cannot detect bind IP for OG810Xi — trunk config not written")
    yield


app = FastAPI(
    title="NGN Fax API",
    description="Send faxes and handle NTT DHCP config via Asterisk AMI (containerized)",
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(_api_key_header)) -> str:
    if not FAX_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured on server")
    if not secrets.compare_digest(api_key, FAX_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


# ---------------------------------------------------------------------------
# AMI Client
# ---------------------------------------------------------------------------

class AMIError(Exception):
    pass


def _ami_command(action: dict[str, str]) -> str:
    """Send a single AMI action and return the raw response."""
    if not AMI_USERNAME or not AMI_SECRET:
        raise AMIError("AMI credentials not configured (AMI_USERNAME / AMI_SECRET)")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((AMI_HOST, AMI_PORT))
        banner = sock.recv(1024).decode()
        if "Asterisk" not in banner:
            raise AMIError(f"Unexpected AMI banner: {banner.strip()}")

        login = (
            "Action: Login\r\n"
            f"Username: {AMI_USERNAME}\r\n"
            f"Secret: {AMI_SECRET}\r\n"
            "\r\n"
        )
        sock.sendall(login.encode())
        resp = _recv_response(sock)
        if "Success" not in resp:
            raise AMIError(f"AMI login failed: {resp.strip()}")

        msg = "".join(f"{k}: {v}\r\n" for k, v in action.items()) + "\r\n"
        sock.sendall(msg.encode())
        resp = _recv_response(sock)

        sock.sendall(b"Action: Logoff\r\n\r\n")
        return resp
    finally:
        sock.close()


def _recv_response(sock: socket.socket, bufsize: int = 4096) -> str:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(bufsize)
        if not chunk:
            break
        data += chunk
    return data.decode(errors="replace")


# ---------------------------------------------------------------------------
# Fax Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/send_fax")
async def send_fax(
    file: UploadFile = File(...),
    number: str = Form(...),
    _key: str = Depends(verify_api_key),
):
    """Accept a PDF and originate an outbound fax call via Asterisk AMI."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    clean_number = "".join(c for c in number if c.isdigit() or c == "+")
    if len(clean_number) < 3:
        raise HTTPException(status_code=400, detail="Invalid fax number")

    fax_dir = "/var/spool/asterisk/fax/outgoing"
    os.makedirs(fax_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=fax_dir, suffix=".pdf", delete=False, prefix="faxout_"
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        os.chmod(tmp_path, 0o644)
    except OSError:
        pass

    log.info("Fax upload saved: %s (%d bytes) -> %s", file.filename, len(content), clean_number)

    try:
        action = {
            "Action": "Originate",
            "Channel": f"PJSIP/{clean_number}@ntt-trunk",
            "Context": "fax-outbound",
            "Exten": "s",
            "Priority": "1",
            "Variable": f"FAXFILE={tmp_path}",
            "CallerID": f'"Fax" <{SIP_FROM_USER}>',
            "Timeout": "60000",
            "Async": "true",
        }
        resp = _ami_command(action)
        if "Success" not in resp:
            raise AMIError(f"Originate failed: {resp.strip()}")
    except AMIError as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "status": "queued",
        "number": clean_number,
        "file": file.filename,
        "tmp_path": tmp_path,
    }


# ---------------------------------------------------------------------------
# NTT DHCP Auto-Configuration
# ---------------------------------------------------------------------------

def _check_ntt_source(request: Request):
    """Verify request comes from an allowed source (MikroTik / server VLAN)."""
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=403, detail="No client IP")
    try:
        addr = ipaddress.IPv4Address(client_ip)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid client IP")
    if not any(addr in net for net in _allowed_networks):
        log.warning("NTT DHCP request rejected from %s", client_ip)
        raise HTTPException(status_code=403, detail="Forbidden")


def _set_ownership(file_path: str) -> None:
    """Set file ownership to UID/GID 1000 (asterisk inside core container), mode 640."""
    try:
        os.chown(file_path, 1000, 1000)
        os.chmod(file_path, 0o640)
    except Exception as exc:
        log.warning("Failed to set ownership on %s: %s", file_path, exc)


def _detect_bind_ip(gateway_ip: str) -> str:
    """Detect the local IP on the same subnet as the gateway."""
    if OG810XI_BIND_IP:
        return OG810XI_BIND_IP
    try:
        gw = ipaddress.IPv4Address(gateway_ip)
        import subprocess
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    iface = ipaddress.IPv4Interface(parts[i + 1])
                    if gw in iface.network:
                        return str(iface.ip)
    except Exception as exc:
        log.warning("Failed to detect bind IP for %s: %s", gateway_ip, exc)
    return ""


def _generate_pjsip_ntt_dynamic_og810xi(bind_ip: str, gw_ip: str, sip_user: str) -> bool:
    """Generate pjsip_ntt_dynamic.conf for OG810Xi direct mode.

    In this mode, Asterisk registers as two SIP clients to OG810Xi (the NTT
    gateway) on the local 192.168.1.x subnet:
    - Voice (ext 10): transport on enp2s0 IP (bind_ip)
    - Fax (ext 11): transport on macvlan IP (OG810XI_FAX_BIND_IP)

    Each transport uses a separate IP so the OG810Xi sees distinct MACs and
    can route DIDs to the correct terminal slot. Requires arp_ignore=1 and
    source-based policy routing on the host to prevent ARP flux.

    Returns True if the file was updated.
    """
    fax_user = OG810XI_SIP_USER_FAX
    fax_bind_ip = OG810XI_FAX_BIND_IP
    config = f"""; pjsip_ntt_dynamic.conf — Auto-generated by faxapi (OG810Xi direct mode)
; DO NOT EDIT — this file is overwritten by faxapi.
; Voice: {bind_ip}:5062 (ext {sip_user}), Fax: {fax_bind_ip}:5062 (ext {fax_user})

; --- Voice transport (enp2s0) ---
[og810xi-udp]
type=transport
protocol=udp
bind={bind_ip}:5062

; --- Fax transport (enp2s0.fax macvlan) ---
[og810xi-fax-udp]
type=transport
protocol=udp
bind={fax_bind_ip}:5063

[ntt-trunk]
type=endpoint
transport=og810xi-udp
context=from-ntt
disallow=all
allow=ulaw
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
dtmf_mode=auto
100rel=yes
trust_id_inbound=yes
send_pai=no
timers=no
allow_overlap=no
aors=ntt-trunk-aor
outbound_auth=

[ntt-trunk-aor]
type=aor
contact=sip:{gw_ip}:5060
qualify_frequency=30

[ntt-trunk-ident]
type=identify
endpoint=ntt-trunk
match={gw_ip}
match=192.168.1.0/24

; --- Voice registration (OG810Xi terminal 1, ext {sip_user}) ---
[ntt-trunk-reg]
type=registration
transport=og810xi-udp
server_uri=sip:{gw_ip}
client_uri=sip:{sip_user}@{gw_ip}
contact_user={sip_user}
retry_interval=30
expiration=300

; --- Fax registration (OG810Xi terminal 2, ext {fax_user}) ---
[ntt-fax-reg]
type=registration
transport=og810xi-fax-udp
server_uri=sip:{gw_ip}
client_uri=sip:{fax_user}@{gw_ip}
contact_user={fax_user}
retry_interval=30
expiration=300
"""
    output_path = "/etc/asterisk/pjsip_ntt_dynamic.conf"
    p = Path(output_path)
    if p.exists() and p.read_text() == config:
        log.info("pjsip_ntt_dynamic.conf unchanged — skipping")
        return False

    p.write_text(config)
    _set_ownership(output_path)
    log.info("Wrote %s (OG810Xi direct: bind=%s gw=%s user=%s)", output_path, bind_ip, gw_ip, sip_user)
    return True


def _generate_pjsip_ntt_dynamic_nat(assigned_ip: str, sip_server: str) -> bool:
    """Generate pjsip_ntt_dynamic.conf for MikroTik NAT mode.

    In this mode, MikroTik clones OG810Xi MAC, gets NTT DHCP lease, and
    dst-nat forwards NTT SIP to Asterisk. No registration needed.

    Returns True if the file was updated.
    """
    acl_permits = [f"permit={sip_server}/32"]
    for rfc1918 in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]:
        acl_permits.append(f"permit={rfc1918}")
    acl_section = "\n".join(acl_permits)

    config = f"""; pjsip_ntt_dynamic.conf — Auto-generated by faxapi (MikroTik NAT mode)
; DO NOT EDIT — this file is overwritten on NTT DHCP change.

[ntt-trunk]
type=endpoint
transport={SIP_TRANSPORT}
context=from-ntt
disallow=all
allow=ulaw
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
from_domain={NTT_SIP_DOMAIN}
from_user={NTT_VOICE_DID}
dtmf_mode=auto
sdp_session=-
100rel=yes
trust_id_inbound=yes
send_pai=no
timers=no
allow_overlap=no
aors=ntt-trunk-aor
outbound_auth=
deny=0.0.0.0/0
{acl_section}

[ntt-trunk-aor]
type=aor
contact=sip:{sip_server}:5060
qualify_frequency=0

[ntt-trunk-ident]
type=identify
endpoint=ntt-trunk
match={sip_server}

"""
    output_path = "/etc/asterisk/pjsip_ntt_dynamic.conf"
    p = Path(output_path)
    if p.exists() and p.read_text() == config:
        log.info("pjsip_ntt_dynamic.conf unchanged — skipping")
        return False

    p.write_text(config)
    _set_ownership(output_path)
    log.info("Wrote %s (NAT mode: ip=%s sip=%s)", output_path, assigned_ip, sip_server)
    return True


def _generate_pjsip_ntt_dynamic(assigned_ip: str, sip_server: str) -> bool:
    """Generate pjsip_ntt_dynamic.conf — dispatches to mode-specific generator."""
    if NTT_MODE == "og810xi":
        bind_ip = _detect_bind_ip(OG810XI_GW_IP)
        if not bind_ip:
            log.error("Cannot detect bind IP for OG810Xi subnet — skipping config generation")
            return False
        return _generate_pjsip_ntt_dynamic_og810xi(bind_ip, OG810XI_GW_IP, OG810XI_SIP_USER)
    else:
        return _generate_pjsip_ntt_dynamic_nat(assigned_ip, sip_server)


def _clean_ntt_local_net(assigned_ip: str, sip_server: str) -> bool:
    """Remove NTT subnets from local_net in the transport config.

    In NAT topology (Asterisk behind MikroTik), NTT subnets must NOT be
    in local_net — otherwise Asterisk won't apply external_media_address
    rewriting for NTT traffic, and SDP will contain private IPs.

    Returns True if the file was modified.
    """
    ntt_net = str(ipaddress.IPv4Interface(f"{assigned_ip}/30").network)
    ntt_entries = {ntt_net, f"{sip_server}/32"}

    transport_path = "/etc/asterisk/pjsip.transports.conf"
    try:
        content = Path(transport_path).read_text()
    except OSError as exc:
        log.warning("Cannot read %s: %s", transport_path, exc)
        return False

    lines = content.splitlines(keepends=True)
    new_lines = []
    removed = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("local_net="):
            net_val = stripped.split("=", 1)[1]
            if net_val in ntt_entries:
                removed.append(net_val)
                continue
        new_lines.append(line)

    if not removed:
        log.info("No NTT local_net entries to remove")
        return False

    Path(transport_path).write_text("".join(new_lines))
    log.info("Cleaned transport config: removed NTT local_net entries %s", removed)
    return True


def _patch_external_addresses(assigned_ip: str) -> bool:
    """Update external_media_address and external_signaling_address.

    Returns True if the file was modified.
    """
    transport_path = "/etc/asterisk/pjsip.transports.conf"
    try:
        content = Path(transport_path).read_text()
    except OSError as exc:
        log.warning("Cannot read %s: %s", transport_path, exc)
        return False

    modified = False
    for key in ("external_media_address", "external_signaling_address"):
        pattern = rf"^{key}=.*$"
        replacement = f"{key}={assigned_ip}"
        new_content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
        if new_content != content:
            content = new_content
            modified = True
            log.info("Patched %s=%s", key, assigned_ip)

    if modified:
        Path(transport_path).write_text(content)

    return modified


def _patch_global_user_agent() -> bool:
    """Suppress User-Agent header in pjsip.conf [global] section.

    Returns True if the file was modified.
    """
    pjsip_path = "/etc/asterisk/pjsip.conf"
    try:
        content = Path(pjsip_path).read_text()
    except OSError as exc:
        log.warning("Cannot read %s: %s", pjsip_path, exc)
        return False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("user_agent="):
            if stripped == "user_agent=":
                log.info("user_agent already suppressed")
                return False
            break

    new_content = re.sub(
        r"^user_agent=.*$", "user_agent=", content, count=1, flags=re.MULTILINE,
    )
    if new_content == content:
        log.warning("Could not find user_agent= line in %s", pjsip_path)
        return False

    Path(pjsip_path).write_text(new_content)
    log.info("Patched %s: user_agent suppressed", pjsip_path)
    return True


# ---------------------------------------------------------------------------
# FreePBX DB helpers (pymysql)
# ---------------------------------------------------------------------------

def _freepbx_db_query(sql: str, params: tuple = ()) -> str | None:
    """Execute a SELECT and return the first column of the first row."""
    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=MYSQL_USER,
            password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            conn.close()
    except pymysql.Error as exc:
        log.warning("FreePBX DB query failed: %s", exc)
        return None


def _freepbx_db_query_all(sql: str, params: tuple = ()) -> list[tuple]:
    """Execute a SELECT and return all rows."""
    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=MYSQL_USER,
            password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        finally:
            conn.close()
    except pymysql.Error as exc:
        log.warning("FreePBX DB query_all failed: %s", exc)
        return []


def _freepbx_db_execute(sql: str, params: tuple = ()) -> bool:
    """Execute an INSERT/UPDATE/DELETE and return success."""
    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=MYSQL_USER,
            password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                return True
        finally:
            conn.close()
    except pymysql.Error as exc:
        log.warning("FreePBX DB execute failed: %s", exc)
        return False


def _update_freepbx_externip(assigned_ip: str) -> None:
    """Update FreePBX kvstore_Sipsettings externip."""
    if _freepbx_db_execute(
        "UPDATE kvstore_Sipsettings SET val = %s WHERE `key` = 'externip'",
        (assigned_ip,),
    ):
        log.info("Updated FreePBX DB externip=%s", assigned_ip)
    else:
        log.warning("Failed to update FreePBX externip")


def _patch_freepbx_localnets(assigned_ip: str, sip_server: str) -> bool:
    """Update FreePBX kvstore_Sipsettings.localnets to include NTT subnets.

    Returns True if the DB was modified.
    """
    raw = _freepbx_db_query(
        "SELECT val FROM kvstore_Sipsettings WHERE `key` = 'localnets'"
    )
    if not raw:
        log.warning("No localnets entry in kvstore_Sipsettings")
        return False

    try:
        localnets = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Cannot parse localnets JSON: %s", raw[:200])
        return False

    if not isinstance(localnets, list):
        log.warning("Unexpected localnets format: %s", type(localnets))
        return False

    ntt_net = str(ipaddress.IPv4Interface(f"{assigned_ip}/30").network)
    nets_to_add = [ntt_net, f"{sip_server}/32"]

    existing = {entry["net"] for entry in localnets if isinstance(entry, dict) and "net" in entry}
    modified = False
    for net_cidr in nets_to_add:
        iface = ipaddress.IPv4Network(net_cidr, strict=False)
        net_addr = str(iface.network_address)
        prefix_len = str(iface.prefixlen)
        if net_addr not in existing:
            localnets.append({"net": net_addr, "mask": prefix_len})
            log.info("Adding local_net to FreePBX DB: %s/%s", net_addr, prefix_len)
            modified = True

    if not modified:
        log.info("FreePBX DB localnets already includes NTT subnets")
        return False

    new_json = json.dumps(localnets)
    if _freepbx_db_execute(
        "UPDATE kvstore_Sipsettings SET val = %s WHERE `key` = 'localnets'",
        (new_json,),
    ):
        log.info("Updated FreePBX DB localnets")
        return True
    log.error("Failed to update FreePBX localnets")
    return False


# ---------------------------------------------------------------------------
# PJSIP reload via AMI
# ---------------------------------------------------------------------------

def _reload_pjsip() -> None:
    """Trigger Asterisk PJSIP reload via AMI Command action."""
    try:
        resp = _ami_command({"Action": "Command", "Command": "pjsip reload"})
        log.info("PJSIP reload via AMI: %s", resp.strip()[:200])
    except AMIError as exc:
        log.error("PJSIP reload failed: %s", exc)


# ---------------------------------------------------------------------------
# NTT state
# ---------------------------------------------------------------------------

_ntt_state: dict = {
    "ntt_ip": None,
    "ntt_gateway": None,
    "last_update": None,
    "updates": [],
}


# ---------------------------------------------------------------------------
# NTT DHCP Endpoints
# ---------------------------------------------------------------------------

@app.post("/ntt-dhcp")
async def ntt_dhcp(
    request: Request,
    ip: str = Form(...),
    gateway: str = Form(...),
    _: None = Depends(_check_ntt_source),
):
    """Handle NTT DHCP notification from MikroTik."""
    try:
        ipaddress.IPv4Address(ip)
        ipaddress.IPv4Address(gateway)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid IP: {exc}")

    sip_server = NTT_SIP_SERVER
    log.info("NTT DHCP notification: ip=%s gateway=%s sip_server=%s mode=%s", ip, gateway, sip_server, NTT_MODE)

    updates = []

    if _generate_pjsip_ntt_dynamic(ip, sip_server):
        updates.append("pjsip_ntt_dynamic.conf")

    # NAT-specific patches (skip in OG810Xi direct mode)
    if NTT_MODE != "og810xi":
        if _clean_ntt_local_net(ip, sip_server):
            updates.append("pjsip.transports.conf:clean_local_net")

        if _patch_external_addresses(ip):
            updates.append("pjsip.transports.conf:external_addresses")

    if _patch_global_user_agent():
        updates.append("pjsip.conf:user_agent")

    if updates:
        _reload_pjsip()
        updates.append("pjsip_reload")

    _ntt_state["ntt_ip"] = ip
    _ntt_state["ntt_gateway"] = gateway
    _ntt_state["last_update"] = datetime.now(timezone.utc).isoformat()
    _ntt_state["updates"] = updates

    log.info("NTT DHCP update complete: %s", updates or "no changes needed")
    return {"status": "ok", "ip": ip, "gateway": gateway, "updates": updates}


@app.get("/ntt-status")
async def ntt_status():
    """Return current NTT IP and last update time."""
    return _ntt_state


# ---------------------------------------------------------------------------
# PBX SQLite helpers
# ---------------------------------------------------------------------------

def _pbx_db() -> sqlite3.Connection:
    """Open PBX SQLite database with row factory."""
    conn = sqlite3.connect(PBX_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _confgen_reload() -> dict:
    """Run confgen and reload Asterisk via AMI."""
    gen = ConfGen(db_path=PBX_DB_PATH)
    return gen.write_and_reload(_ami_command)


# ---------------------------------------------------------------------------
# Extension Management — /extensions (backward compatible) + /pbx/extensions
# ---------------------------------------------------------------------------

@app.get("/extensions")
async def list_extensions(_key: str = Depends(verify_api_key)):
    """List all PJSIP extensions from the PBX database."""
    conn = _pbx_db()
    rows = conn.execute("SELECT ext, name, password, context, mailbox, recording FROM extensions ORDER BY ext").fetchall()
    conn.close()
    return {"extensions": [
        {"extension": r["ext"], "name": r["name"], "tech": "pjsip", "context": r["context"]}
        for r in rows
    ]}


@app.get("/extensions/{ext}")
async def get_extension(ext: str, _key: str = Depends(verify_api_key)):
    """Get a single extension by number."""
    conn = _pbx_db()
    row = conn.execute("SELECT * FROM extensions WHERE ext = ?", (ext,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Extension {ext} not found")
    return dict(row)


@app.post("/extensions")
async def create_extension(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Create a PJSIP extension via PBX SQLite + confgen.

    Body JSON: {"extension": "001", "name": "User Name", "password": "1234"}
    """
    body = await request.json()
    ext = body.get("extension", "")
    name = body.get("name", ext)
    password = body.get("password", f"wf4a{ext}")
    call_group = body.get("call_group", "1")
    pickup_group = body.get("pickup_group", "1")

    if not ext or not ext.isdigit():
        raise HTTPException(status_code=400, detail="Invalid extension number")

    conn = _pbx_db()
    try:
        conn.execute(
            "INSERT INTO extensions (ext, name, password, call_group, pickup_group) VALUES (?, ?, ?, ?, ?)",
            (ext, name, password, call_group, pickup_group),
        )
        # Also add to ring group 200 (all extensions)
        rg = conn.execute("SELECT id FROM ring_groups WHERE number = '200'").fetchone()
        if rg:
            conn.execute(
                "INSERT OR IGNORE INTO ring_group_members (group_id, ext) VALUES (?, ?)",
                (rg["id"], ext),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail=f"Extension {ext} already exists")
    conn.close()

    # Regenerate configs and reload Asterisk
    try:
        result = _confgen_reload()
        log.info("Created extension %s (%s) — %s", ext, name, result)
    except Exception as exc:
        log.error("confgen/reload failed after creating %s: %s", ext, exc)

    return {"status": "created", "extension": ext, "name": name}


@app.put("/extensions/{ext}")
async def update_extension(ext: str, request: Request, _key: str = Depends(verify_api_key)):
    """Update an existing extension."""
    body = await request.json()
    conn = _pbx_db()
    row = conn.execute("SELECT * FROM extensions WHERE ext = ?", (ext,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Extension {ext} not found")

    name = body.get("name", row["name"])
    password = body.get("password", row["password"])
    context = body.get("context", row["context"])
    mailbox = body.get("mailbox", row["mailbox"])
    recording = body.get("recording", row["recording"])
    call_group = body.get("call_group", row["call_group"])
    pickup_group = body.get("pickup_group", row["pickup_group"])

    conn.execute(
        "UPDATE extensions SET name=?, password=?, context=?, mailbox=?, recording=?, call_group=?, pickup_group=?, updated_at=datetime('now') WHERE ext=?",
        (name, password, context, mailbox, recording, call_group, pickup_group, ext),
    )
    conn.commit()
    conn.close()

    try:
        _confgen_reload()
    except Exception as exc:
        log.error("confgen/reload failed after updating %s: %s", ext, exc)

    return {"status": "updated", "extension": ext, "name": name}


@app.delete("/extensions/{ext}")
async def delete_extension(ext: str, _key: str = Depends(verify_api_key)):
    """Delete a PJSIP extension."""
    conn = _pbx_db()
    row = conn.execute("SELECT ext FROM extensions WHERE ext = ?", (ext,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Extension {ext} not found")

    conn.execute("DELETE FROM ring_group_members WHERE ext = ?", (ext,))
    conn.execute("DELETE FROM extensions WHERE ext = ?", (ext,))
    conn.commit()
    conn.close()

    try:
        _confgen_reload()
    except Exception as exc:
        log.error("confgen/reload failed after deleting %s: %s", ext, exc)

    log.info("Deleted extension %s", ext)
    return {"status": "deleted", "extension": ext}


@app.post("/extensions/reload")
async def reload_extensions(_key: str = Depends(verify_api_key)):
    """Regenerate configs and reload Asterisk."""
    try:
        result = _confgen_reload()
        return {"status": "reloaded", "details": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# PBX Ring Groups
# ---------------------------------------------------------------------------

@app.get("/pbx/ring-groups")
async def list_ring_groups(_key: str = Depends(verify_api_key)):
    """List all ring groups with their members."""
    conn = _pbx_db()
    groups = conn.execute("SELECT * FROM ring_groups ORDER BY id").fetchall()
    result = []
    for g in groups:
        members = conn.execute(
            "SELECT ext FROM ring_group_members WHERE group_id = ? ORDER BY ext",
            (g["id"],),
        ).fetchall()
        result.append({
            **dict(g),
            "members": [m["ext"] for m in members],
        })
    conn.close()
    return {"ring_groups": result}


@app.put("/pbx/ring-groups/{group_id}/members")
async def update_ring_group_members(
    group_id: int, request: Request, _key: str = Depends(verify_api_key),
):
    """Update ring group members. Body: {"members": ["001", "002", ...]}"""
    body = await request.json()
    members = body.get("members", [])

    conn = _pbx_db()
    rg = conn.execute("SELECT id FROM ring_groups WHERE id = ?", (group_id,)).fetchone()
    if not rg:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ring group {group_id} not found")

    conn.execute("DELETE FROM ring_group_members WHERE group_id = ?", (group_id,))
    for ext in members:
        conn.execute(
            "INSERT OR IGNORE INTO ring_group_members (group_id, ext) VALUES (?, ?)",
            (group_id, ext),
        )
    conn.commit()
    conn.close()

    try:
        _confgen_reload()
    except Exception as exc:
        log.error("confgen/reload failed: %s", exc)

    return {"status": "updated", "group_id": group_id, "members": members}


# ---------------------------------------------------------------------------
# PBX Day/Night Modes
# ---------------------------------------------------------------------------

@app.get("/pbx/day-night")
async def list_day_night(_key: str = Depends(verify_api_key)):
    """List day/night modes with current state."""
    conn = _pbx_db()
    modes = conn.execute("SELECT * FROM day_night_modes ORDER BY id").fetchall()
    conn.close()
    return {"modes": [dict(m) for m in modes]}


@app.post("/pbx/day-night/{mode_id}/toggle")
async def toggle_day_night(mode_id: int, _key: str = Depends(verify_api_key)):
    """Toggle day/night mode via AstDB."""
    conn = _pbx_db()
    mode = conn.execute("SELECT * FROM day_night_modes WHERE id = ?", (mode_id,)).fetchone()
    if not mode:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Day/night mode {mode_id} not found")

    new_state = "night" if mode["current_state"] == "day" else "day"
    conn.execute("UPDATE day_night_modes SET current_state = ? WHERE id = ?", (new_state, mode_id))
    conn.commit()
    conn.close()

    # Also update AstDB — FreePBX uses "C" prefix: DAYNIGHT/C0, DAYNIGHT/C1, etc.
    db_key = f"C{mode_id}"
    db_val = "NIGHT" if new_state == "night" else "DAY"
    try:
        _ami_command({"Action": "Command", "Command": f"database put DAYNIGHT {db_key} {db_val}"})
    except AMIError as exc:
        log.error("Failed to update AstDB DAYNIGHT/%s: %s", db_key, exc)

    return {"mode_id": mode_id, "current_state": new_state, "name": mode["name"]}


# ---------------------------------------------------------------------------
# PBX Routes
# ---------------------------------------------------------------------------

@app.get("/pbx/routes/outbound")
async def list_outbound_routes(_key: str = Depends(verify_api_key)):
    """List outbound routes."""
    conn = _pbx_db()
    routes = conn.execute("SELECT * FROM outbound_routes ORDER BY priority").fetchall()
    conn.close()
    return {"routes": [dict(r) for r in routes]}


@app.get("/pbx/routes/inbound")
async def list_inbound_routes(_key: str = Depends(verify_api_key)):
    """List inbound DID routes."""
    conn = _pbx_db()
    routes = conn.execute("SELECT * FROM inbound_routes ORDER BY id").fetchall()
    conn.close()
    return {"routes": [dict(r) for r in routes]}


# ---------------------------------------------------------------------------
# PBX Feature Codes
# ---------------------------------------------------------------------------

@app.get("/pbx/feature-codes")
async def list_feature_codes(_key: str = Depends(verify_api_key)):
    """List enabled feature codes."""
    conn = _pbx_db()
    codes = conn.execute("SELECT * FROM feature_codes WHERE enabled = 1 ORDER BY code").fetchall()
    conn.close()
    return {"feature_codes": [dict(c) for c in codes]}


# ---------------------------------------------------------------------------
# PBX IVR Menus
# ---------------------------------------------------------------------------

@app.get("/pbx/ivr")
async def list_ivr(_key: str = Depends(verify_api_key)):
    """List IVR menus with entries."""
    conn = _pbx_db()
    menus = conn.execute("SELECT * FROM ivr_menus ORDER BY id").fetchall()
    result = []
    for m in menus:
        entries = conn.execute(
            "SELECT digit, destination FROM ivr_entries WHERE ivr_id = ? ORDER BY digit",
            (m["id"],),
        ).fetchall()
        result.append({
            **dict(m),
            "entries": [dict(e) for e in entries],
        })
    conn.close()
    return {"ivr_menus": result}


# ---------------------------------------------------------------------------
# PBX System Status
# ---------------------------------------------------------------------------

@app.get("/pbx/status")
async def pbx_status(_key: str = Depends(verify_api_key)):
    """Get Asterisk status: uptime, channels, registrations."""
    status = {}
    try:
        resp = _ami_command({"Action": "Command", "Command": "core show uptime"})
        status["uptime"] = resp.strip()
    except AMIError as exc:
        status["uptime"] = f"error: {exc}"

    try:
        resp = _ami_command({"Action": "Command", "Command": "core show channels count"})
        status["channels"] = resp.strip()
    except AMIError as exc:
        status["channels"] = f"error: {exc}"

    try:
        resp = _ami_command({"Action": "Command", "Command": "pjsip show endpoints"})
        # Count registered endpoints
        registered = resp.count("Avail")
        total = resp.count("type=endpoint") if "type=endpoint" in resp else resp.count("<")
        status["endpoints_registered"] = registered
        status["endpoints_total"] = total
    except AMIError as exc:
        status["endpoints"] = f"error: {exc}"

    return status


@app.get("/pbx/active-calls")
async def pbx_active_calls(_key: str = Depends(verify_api_key)):
    """List current active channels."""
    try:
        resp = _ami_command({"Action": "Command", "Command": "core show channels"})
        return {"channels": resp.strip()}
    except AMIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/pbx/reload")
async def pbx_reload(_key: str = Depends(verify_api_key)):
    """Force full config regeneration + AMI reload."""
    try:
        result = _confgen_reload()
        return {"status": "reloaded", "details": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Call Origination with Recording
# ---------------------------------------------------------------------------

RECORDING_DIR = "/var/spool/asterisk/recording"


@app.post("/calls/originate")
async def originate_call(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Originate a recorded call between two extensions.

    Body JSON: {"caller_extension": "202", "target_extension": "301", "call_id": "abc123"}
    """
    body = await request.json()
    caller = body.get("caller_extension", "")
    target = body.get("target_extension", "")
    call_id = body.get("call_id", "")

    if not caller or not target or not call_id:
        raise HTTPException(status_code=400, detail="caller_extension, target_extension, call_id required")

    os.makedirs(RECORDING_DIR, exist_ok=True)
    recording_path = f"{RECORDING_DIR}/{call_id}.wav"

    try:
        action = {
            "Action": "Originate",
            "Channel": f"PJSIP/{caller}",
            "Context": "recorded-call",
            "Exten": target,
            "Priority": "1",
            "Variable": f"CALL_ID={call_id},RECORDING_PATH={recording_path}",
            "CallerID": f'"{caller}" <{caller}>',
            "Timeout": "30000",
            "Async": "true",
        }
        resp = _ami_command(action)
        if "Success" not in resp:
            raise AMIError(f"Originate failed: {resp.strip()}")
    except AMIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    log.info("Call originated: %s -> %s (call_id=%s)", caller, target, call_id)
    return {"status": "ringing", "call_id": call_id, "caller": caller, "target": target}


@app.get("/calls/{call_id}/status")
async def call_status(call_id: str, _key: str = Depends(verify_api_key)):
    """Check if call recording exists (completed) or channel is active."""
    recording_path = f"{RECORDING_DIR}/{call_id}.wav"
    if Path(recording_path).exists():
        size = Path(recording_path).stat().st_size
        return {"call_id": call_id, "status": "completed", "recording_size": size}

    # Check if channel is still active
    try:
        resp = _ami_command({"Action": "Command", "Command": "core show channels"})
        if call_id in resp:
            return {"call_id": call_id, "status": "in_progress"}
    except AMIError:
        pass

    return {"call_id": call_id, "status": "unknown"}


@app.get("/calls/{call_id}/recording")
async def get_recording(call_id: str, _key: str = Depends(verify_api_key)):
    """Serve the call recording WAV file."""
    from fastapi.responses import FileResponse

    recording_path = f"{RECORDING_DIR}/{call_id}.wav"
    if not Path(recording_path).exists():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(recording_path, media_type="audio/wav", filename=f"{call_id}.wav")


# ---------------------------------------------------------------------------
# PBX Call Forward Unconditional (CFU) via AstDB
# ---------------------------------------------------------------------------

@app.post("/pbx/cfu")
async def set_cfu(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Set CFU (Call Forward Unconditional) for an extension.

    Body JSON: {"extension": "301", "forward_to": "3101"}
    Sets AstDB: CFU/301 = 3101
    """
    body = await request.json()
    ext = body.get("extension", "")
    forward_to = body.get("forward_to", "")

    if not ext or not forward_to:
        raise HTTPException(status_code=400, detail="extension and forward_to required")

    try:
        resp = _ami_command({
            "Action": "Command",
            "Command": f"database put CFU {ext} {forward_to}",
        })
        if "Updated" not in resp and "entry" not in resp.lower():
            log.warning("CFU set response: %s", resp.strip()[:200])
    except AMIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    log.info("CFU set: %s -> %s", ext, forward_to)
    return {"status": "ok", "extension": ext, "forward_to": forward_to}


@app.get("/pbx/cfu/{ext}")
async def get_cfu(ext: str, _key: str = Depends(verify_api_key)):
    """Get current CFU target for an extension."""
    try:
        resp = _ami_command({
            "Action": "Command",
            "Command": f"database get CFU {ext}",
        })
        # Response contains "Value: <target>" on success
        for line in resp.splitlines():
            if "Value:" in line:
                value = line.split("Value:", 1)[1].strip()
                return {"extension": ext, "forward_to": value}
        return {"extension": ext, "forward_to": None}
    except AMIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.delete("/pbx/cfu/{ext}")
async def clear_cfu(ext: str, _key: str = Depends(verify_api_key)):
    """Clear CFU for an extension."""
    try:
        _ami_command({
            "Action": "Command",
            "Command": f"database del CFU {ext}",
        })
    except AMIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    log.info("CFU cleared: %s", ext)
    return {"status": "ok", "extension": ext}


# ---------------------------------------------------------------------------
# Phone Display Name Push (Grandstream HTTP API)
# ---------------------------------------------------------------------------

@app.post("/phone/display-name")
async def set_phone_display_name(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Push display name (P3) to a Grandstream phone via its HTTP API.

    Body JSON: {"phone_ip": "10.0.7.12", "display_name": "田中太郎"}
    """
    body = await request.json()
    phone_ip = body.get("phone_ip", "")
    display_name = body.get("display_name", "")

    if not phone_ip or not display_name:
        raise HTTPException(status_code=400, detail="phone_ip and display_name required")

    if not PHONE_ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="PHONE_ADMIN_PASSWORD not configured")

    base_url = f"http://{phone_ip}/cgi-bin"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Login
        try:
            login_resp = await client.post(
                f"{base_url}/dologin",
                data={"password": PHONE_ADMIN_PASSWORD},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"http://{phone_ip}/",
                    "Origin": f"http://{phone_ip}",
                },
            )
            login_data = login_resp.json()
            if login_data.get("response") != "success":
                raise HTTPException(status_code=502, detail=f"Phone login failed: {login_data}")
            sid = login_data["body"]["sid"]
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Cannot reach phone at {phone_ip}: {exc}")

        # Push P3 (Account Name / Display Name)
        cookies = {k: v for k, v in login_resp.cookies.items()}
        try:
            push_resp = await client.post(
                f"{base_url}/api.values.post",
                data={"sid": sid, "P3": display_name},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"http://{phone_ip}/",
                },
                cookies=cookies,
            )
            push_data = push_resp.json()
            if push_data.get("response") != "success":
                log.warning("Phone display-name push response: %s", push_data)
        except httpx.RequestError as exc:
            log.warning("Phone display-name push failed: %s", exc)

    log.info("Phone display name set: %s -> %s", phone_ip, display_name)
    return {"status": "ok", "phone_ip": phone_ip, "display_name": display_name}


# ---------------------------------------------------------------------------
# OG810Xi SIP client management
# ---------------------------------------------------------------------------
from bs4 import BeautifulSoup


def _og810xi_auth():
    """Return httpx basic auth tuple."""
    return (OG810XI_USERNAME, OG810XI_PASSWORD)


def _og810xi_parse_clients(html: str) -> dict:
    """Parse the tel_ipgw_main page and return SIP clients and GW entries."""
    soup = BeautifulSoup(html, "html.parser")

    # Parse IP端末テーブル (SIP client table)
    clients = []
    for i in range(1, 9):
        ext_input = soup.find("input", {"id": f"INT_NUM{i}"})
        name_input = soup.find("input", {"id": f"INTIP_NAME{i}"})
        tel_input = soup.find("input", {"id": f"ADDRESSER_TEL{i}"})
        if not ext_input:
            continue
        # IP and MAC are in plain text table cells — find by row
        row_cells = ext_input.find_parent("tr").find_all("td", class_="matrix_item")
        ip_addr = row_cells[4].get_text(strip=True) if len(row_cells) > 4 else ""
        mac_addr = row_cells[5].get_text(strip=True) if len(row_cells) > 5 else ""
        clients.append({
            "slot": i,
            "extension": ext_input.get("value", ""),
            "name": name_input.get("value", "") if name_input else "",
            "caller_id": tel_input.get("value", "") if tel_input else "",
            "ip": ip_addr,
            "mac": mac_addr,
        })

    # Parse GW装置テーブル (Gateway table)
    gateways = []
    for i in range(1, 9):
        name_input = soup.find("input", {"id": f"GW_NAME{i}"})
        tel_input = soup.find("input", {"id": f"GW_ADDRESSER_TEL_NUM{i}"})
        mac_input = soup.find("input", {"id": f"GW_MAC_ADDR{i}"})
        ip_input = soup.find("input", {"id": f"GW_IP_ADDR{i}"})
        if not name_input:
            continue
        # Check which radio is selected for 払い出し番号選択
        all_radio = soup.find("input", {"id": f"GW_TEL_H_INIT{i}"})
        income_radio = soup.find("input", {"id": f"GW_TEL_H_RENEW{i}"})
        number_mode = "all"
        if income_radio and income_radio.get("checked"):
            number_mode = "income"
        gateways.append({
            "slot": i,
            "name": name_input.get("value", ""),
            "caller_id": tel_input.get("value", "") if tel_input else "",
            "number_mode": number_mode,
            "mac": mac_input.get("value", "") if mac_input else "",
            "ip": ip_input.get("value", "") if ip_input else "",
        })

    # Extract SESSION_ID
    session_input = soup.find("input", {"id": "SESSION_ID"})
    session_id = session_input.get("value", "") if session_input else ""

    return {"clients": clients, "gateways": gateways, "session_id": session_id}


async def _og810xi_get_page() -> tuple[str, str]:
    """Fetch the SIP client page. Returns (html, session_id)."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{OG810XI_URL}/index.cgi/tel_ipgw_main",
            auth=_og810xi_auth(),
        )
        resp.raise_for_status()
        parsed = _og810xi_parse_clients(resp.text)
        return resp.text, parsed["session_id"]


@app.get("/og810xi/clients", dependencies=[Depends(verify_api_key)])
async def og810xi_list_clients():
    """List all SIP clients and GW entries on OG810Xi."""
    try:
        html, _ = await _og810xi_get_page()
        return _og810xi_parse_clients(html)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"OG810Xi unreachable: {exc}")


@app.put("/og810xi/clients/{slot}", dependencies=[Depends(verify_api_key)])
async def og810xi_update_client(
    slot: int,
    extension: str = Form(...),
    name: str = Form(""),
    caller_id: str = Form("0312345678"),
):
    """Update an IP端末 (SIP client) slot (1-8)."""
    if slot < 1 or slot > 8:
        raise HTTPException(status_code=400, detail="Slot must be 1-8")
    if not extension or len(extension) > 2:
        raise HTTPException(status_code=400, detail="Extension must be 1-2 digits")

    try:
        html, session_id = await _og810xi_get_page()
        parsed = _og810xi_parse_clients(html)

        # Build form data — must include ALL slots to avoid clearing them
        form_data = {"SESSION_ID": session_id, "UPDATE_BUTTON": "設定保存"}
        for c in parsed["clients"]:
            n = c["slot"]
            if n == slot:
                form_data[f"INT_NUM{n}"] = extension
                form_data[f"INTIP_NAME{n}"] = name or f"IP Phone{n}"
                form_data[f"ADDRESSER_TEL{n}"] = caller_id
            else:
                form_data[f"INT_NUM{n}"] = c["extension"]
                form_data[f"INTIP_NAME{n}"] = c["name"]
                form_data[f"ADDRESSER_TEL{n}"] = c["caller_id"]
        for g in parsed["gateways"]:
            n = g["slot"]
            form_data[f"GW_NAME{n}"] = g["name"]
            form_data[f"GW_ADDRESSER_TEL_NUM{n}"] = g["caller_id"]
            form_data[f"GW_TEL_H{n}"] = g["number_mode"]
            form_data[f"GW_MAC_ADDR{n}"] = g["mac"]
            form_data[f"GW_IP_ADDR{n}"] = g["ip"]

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OG810XI_URL}/index.cgi/tel_ipgw_main_set",
                data=form_data,
                auth=_og810xi_auth(),
            )
            resp.raise_for_status()

        log.info("OG810Xi client slot %d updated: ext=%s name=%s", slot, extension, name)
        return {"status": "ok", "slot": slot, "extension": extension, "name": name, "caller_id": caller_id}

    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"OG810Xi unreachable: {exc}")


@app.put("/og810xi/gateways/{slot}", dependencies=[Depends(verify_api_key)])
async def og810xi_update_gateway(
    slot: int,
    name: str = Form(""),
    caller_id: str = Form("0312345678"),
    mac: str = Form(""),
    ip: str = Form(""),
    number_mode: str = Form("all"),
):
    """Update a GW装置 (gateway) slot (1-8)."""
    if slot < 1 or slot > 8:
        raise HTTPException(status_code=400, detail="Slot must be 1-8")
    if number_mode not in ("all", "income"):
        raise HTTPException(status_code=400, detail="number_mode must be 'all' or 'income'")

    try:
        html, session_id = await _og810xi_get_page()
        parsed = _og810xi_parse_clients(html)

        form_data = {"SESSION_ID": session_id, "UPDATE_BUTTON": "設定保存"}
        for c in parsed["clients"]:
            n = c["slot"]
            form_data[f"INT_NUM{n}"] = c["extension"]
            form_data[f"INTIP_NAME{n}"] = c["name"]
            form_data[f"ADDRESSER_TEL{n}"] = c["caller_id"]
        for g in parsed["gateways"]:
            n = g["slot"]
            if n == slot:
                form_data[f"GW_NAME{n}"] = name or f"GW{n}"
                form_data[f"GW_ADDRESSER_TEL_NUM{n}"] = caller_id
                form_data[f"GW_TEL_H{n}"] = number_mode
                form_data[f"GW_MAC_ADDR{n}"] = mac
                form_data[f"GW_IP_ADDR{n}"] = ip
            else:
                form_data[f"GW_NAME{n}"] = g["name"]
                form_data[f"GW_ADDRESSER_TEL_NUM{n}"] = g["caller_id"]
                form_data[f"GW_TEL_H{n}"] = g["number_mode"]
                form_data[f"GW_MAC_ADDR{n}"] = g["mac"]
                form_data[f"GW_IP_ADDR{n}"] = g["ip"]

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OG810XI_URL}/index.cgi/tel_ipgw_main_set",
                data=form_data,
                auth=_og810xi_auth(),
            )
            resp.raise_for_status()

        log.info("OG810Xi gateway slot %d updated: name=%s mac=%s ip=%s", slot, name, mac, ip)
        return {"status": "ok", "slot": slot, "name": name, "caller_id": caller_id, "mac": mac, "ip": ip}

    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"OG810Xi unreachable: {exc}")


@app.delete("/og810xi/clients/{slot}", dependencies=[Depends(verify_api_key)])
async def og810xi_delete_client(slot: int):
    """Delete an IP端末 (SIP client) slot (1-8)."""
    if slot < 1 or slot > 8:
        raise HTTPException(status_code=400, detail="Slot must be 1-8")

    try:
        _, session_id = await _og810xi_get_page()
        form_data = {
            "SESSION_ID": session_id,
            "TARGET_ENTRY_NO": str(slot),
            "TEL_CLASS": "ip",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OG810XI_URL}/index.cgi/tel_ipgw_main_del",
                data=form_data,
                auth=_og810xi_auth(),
            )
            resp.raise_for_status()

        log.info("OG810Xi client slot %d deleted", slot)
        return {"status": "ok", "slot": slot, "deleted": "client"}

    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"OG810Xi unreachable: {exc}")


@app.delete("/og810xi/gateways/{slot}", dependencies=[Depends(verify_api_key)])
async def og810xi_delete_gateway(slot: int):
    """Delete a GW装置 (gateway) slot (1-8)."""
    if slot < 1 or slot > 8:
        raise HTTPException(status_code=400, detail="Slot must be 1-8")

    try:
        _, session_id = await _og810xi_get_page()
        form_data = {
            "SESSION_ID": session_id,
            "TARGET_ENTRY_NO": str(slot),
            "TEL_CLASS": "gw",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OG810XI_URL}/index.cgi/tel_ipgw_main_del",
                data=form_data,
                auth=_og810xi_auth(),
            )
            resp.raise_for_status()

        log.info("OG810Xi gateway slot %d deleted", slot)
        return {"status": "ok", "slot": slot, "deleted": "gateway"}

    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"OG810Xi unreachable: {exc}")


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    uvicorn.run("fax_api:app", host="0.0.0.0", port=int(os.environ.get("FAX_API_PORT", "8010")))

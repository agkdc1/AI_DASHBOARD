"""Auth proxy: exchange Authentik OIDC token for InvenTree API token server-side.

Flutter calls POST /auth/inventree-token with an oidc_access_token (from
Authentik). This proxy handles the django-allauth headless OIDC flow
server-to-server, returning an InvenTree API token.
"""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
log = logging.getLogger(__name__)

# Authentik outpost for forward-auth validation (server-side call)
_AUTHENTIK_OUTPOST_URL = (
    "https://auth.your-domain.com/outpost.goauthentik.io/auth/nginx"
)
# Use a host that IS configured in the Authentik outpost
_OUTPOST_HOST = "portal.your-domain.com"

_INVENTREE_URL = "http://inventree-server.shinbee.svc.cluster.local:8000"


class TokenRequest(BaseModel):
    oidc_access_token: str


class TokenResponse(BaseModel):
    token: str


@router.get("/auth/session")
async def check_session(request: Request):
    """Validate Authentik session and return user info.

    The Flutter client sends the Authentik proxy cookie (withCredentials).
    We forward it to the Authentik outpost to validate and extract user info.
    No InvenTree dependency — Authentik is the sole identity source.
    """
    # Forward all cookies from the browser request
    cookie_header = request.headers.get("cookie", "")
    if not cookie_header:
        raise HTTPException(status_code=401, detail="No session cookie")

    # Authentik outpost nginx auth requires X-Original-URL to reconstruct
    # the forwarded request. Without it, the outpost returns 500
    # "failed to detect a forward URL from nginx".
    original_url = f"https://{_OUTPOST_HOST}/"
    async with httpx.AsyncClient(verify=True, timeout=10) as client:
        resp = await client.get(
            _AUTHENTIK_OUTPOST_URL,
            headers={
                "Cookie": cookie_header,
                "X-Original-URL": original_url,
                "X-Forwarded-Host": _OUTPOST_HOST,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Scheme": "https",
            },
        )

    if resp.status_code != 200:
        log.info(
            "Authentik session check failed: status=%s body=%s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(status_code=401, detail="Session invalid or expired")

    email = (resp.headers.get("X-authentik-email") or "").strip()
    name = (resp.headers.get("X-authentik-name") or "").strip()
    username = (resp.headers.get("X-authentik-username") or "").strip()

    if not email:
        raise HTTPException(status_code=401, detail="No email in Authentik session")

    return {
        "email": email,
        "display_name": name or username or email,
        "username": username,
    }


def _extract_cookies(resp: httpx.Response, client: httpx.AsyncClient) -> None:
    """Extract cookies from Set-Cookie headers and set them on the client.

    httpx won't store cookies when the Set-Cookie domain (.your-domain.com)
    doesn't match the request URL (internal K8s service URL). We manually
    parse and set all cookies from each response.
    """
    for header_val in resp.headers.get_list("set-cookie"):
        if "=" in header_val:
            name_value = header_val.split(";")[0]  # strip attributes
            name, _, value = name_value.partition("=")
            name = name.strip()
            value = value.strip()
            if name and value:
                client.cookies.set(name, value)


@router.post("/auth/inventree-token", response_model=TokenResponse)
async def exchange_inventree_token(req: TokenRequest):
    """Exchange an Authentik OIDC access token for an InvenTree API token."""
    # Use internal URL but set Host header for Django ALLOWED_HOSTS.
    _host_header = {"Host": "portal.your-domain.com"}
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        # Step 1: Get CSRF cookie from InvenTree.
        config_resp = await client.get(
            f"{_INVENTREE_URL}/api/auth/v1/config",
            headers=_host_header,
        )
        _extract_cookies(config_resp, client)
        csrf_token = str(client.cookies.get("csrftoken", ""))
        log.info(
            "step1: config status=%s csrf=%s",
            config_resp.status_code,
            csrf_token[:20] if csrf_token else "NONE",
        )

        # Step 2: Exchange via allauth headless provider/token.
        # InvenTree uses openid_connect provider with provider_id "authentik".
        auth_resp = await client.post(
            f"{_INVENTREE_URL}/api/auth/v1/auth/provider/token",
            json={
                "provider": "openid_connect",
                "process": "login",
                "token": {
                    "client_id": "inventree-oidc",
                    "id_provider": "authentik",
                    "access_token": req.oidc_access_token,
                },
            },
            headers={**_host_header, "X-CSRFToken": csrf_token},
        )
        _extract_cookies(auth_resp, client)

        data = auth_resp.json()
        session_token = data.get("meta", {}).get("session_token")
        cookie_names = [c.name for c in client.cookies.jar]
        log.info(
            "step2: provider/token status=%s session_token=%s cookies=%s",
            auth_resp.status_code,
            "present" if session_token else "missing",
            cookie_names,
        )

        # Step 2b: Handle provider_signup flow.
        if auth_resp.status_code == 401:
            flows = [
                f.get("id") for f in data.get("data", {}).get("flows", [])
            ]
            log.info("step2b: 401 flows=%s", flows)
            if "provider_signup" in flows:
                csrf_token = str(client.cookies.get("csrftoken", csrf_token))
                signup_headers = {**_host_header, "X-CSRFToken": csrf_token}
                if session_token:
                    signup_headers["X-Session-Token"] = session_token
                signup_resp = await client.post(
                    f"{_INVENTREE_URL}/api/auth/v1/auth/provider/signup",
                    json={},
                    headers=signup_headers,
                )
                _extract_cookies(signup_resp, client)
                log.info(
                    "step2b: provider/signup status=%s body=%s",
                    signup_resp.status_code,
                    signup_resp.text[:500],
                )
                if signup_resp.status_code == 200:
                    data = signup_resp.json()
                    session_token = data.get("meta", {}).get(
                        "session_token", session_token
                    )
                    auth_resp = signup_resp
                else:
                    raise HTTPException(
                        signup_resp.status_code,
                        f"InvenTree signup failed: {signup_resp.text[:500]}",
                    )

        if auth_resp.status_code != 200:
            detail = auth_resp.text[:500]
            log.warning(
                "allauth headless failed: status=%s detail=%s",
                auth_resp.status_code,
                detail,
            )
            raise HTTPException(
                auth_resp.status_code,
                f"InvenTree auth failed: {detail}",
            )

        # Step 3: Get InvenTree API token using the session.
        session_headers: dict = {**_host_header}
        if session_token:
            session_headers["X-Session-Token"] = session_token

        token_resp = await client.get(
            f"{_INVENTREE_URL}/api/user/token/",
            headers=session_headers,
        )
        log.info(
            "step3: user/token status=%s cookies=%s",
            token_resp.status_code,
            [c.name for c in client.cookies.jar],
        )

        if token_resp.status_code != 200:
            log.warning(
                "API token fetch failed: status=%s body=%s",
                token_resp.status_code,
                token_resp.text[:300],
            )
            raise HTTPException(
                token_resp.status_code, "Failed to get InvenTree API token"
            )

        api_token = token_resp.json().get("token")
        if not api_token:
            raise HTTPException(502, "No token in InvenTree response")

        return TokenResponse(token=api_token)

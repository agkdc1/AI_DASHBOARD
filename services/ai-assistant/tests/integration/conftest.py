"""Fixtures for integration tests against live production services.

Run with: RUN_INTEGRATION=1 pytest -m integration -v
"""

import os
import subprocess
import sys

import httpx
import pytest

# ── Ensure ai_assistant/ is on sys.path ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION", "0") == "1"

skip_unless_integration = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="RUN_INTEGRATION not set",
)

# Apply both markers to all tests in the integration/ directory
pytestmark = [pytest.mark.integration, skip_unless_integration]


# ─────────────────────────────────────────────────────────────────────
# Token / credential retrieval (session-scoped for efficiency)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def inventree_token() -> str:
    """Get InvenTree API token via K8s exec into Django shell."""
    cmd = [
        "sudo", "KUBECONFIG=/etc/rancher/k3s/k3s.yaml",
        "kubectl", "-n", "shinbee", "exec", "deployment/inventree-server", "--",
        "python", "manage.py", "shell", "-c",
        (
            "from rest_framework.authtoken.models import Token; "
            "from django.contrib.auth import get_user_model; "
            "user = get_user_model().objects.get(email='admin@your-domain.com'); "
            "token, _ = Token.objects.get_or_create(user=user); "
            "print(token.key)"
        ),
    ]
    try:
        result = subprocess.run(
            " ".join(cmd), shell=True, capture_output=True, text=True, timeout=30,
        )
        token = result.stdout.strip()
        if not token:
            pytest.skip("Could not obtain InvenTree token")
        return token
    except Exception as e:
        pytest.skip(f"InvenTree token retrieval failed: {e}")


@pytest.fixture(scope="session")
def vikunja_token() -> str:
    """Get Vikunja API token from env or K8s secret."""
    token = os.environ.get("VIKUNJA_TOKEN", "")
    if not token:
        try:
            result = subprocess.run(
                "sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl -n intranet get secret vikunja-api-token -o jsonpath='{.data.token}' | base64 -d",
                shell=True, capture_output=True, text=True, timeout=15,
            )
            token = result.stdout.strip()
        except Exception:
            pass
    if not token:
        pytest.skip("No Vikunja token available")
    return token


@pytest.fixture(scope="session")
def faxapi_base_url() -> str:
    return os.environ.get("FAXAPI_URL", "http://10.0.0.254:8010")


# ─────────────────────────────────────────────────────────────────────
# HTTP clients (session-scoped)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def inventree_client(inventree_token) -> httpx.Client:
    """Synchronous httpx client for InvenTree API."""
    client = httpx.Client(
        base_url="https://portal.your-domain.com",
        headers={"Authorization": f"Token {inventree_token}"},
        timeout=30.0,
        verify=True,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def vikunja_client(vikunja_token) -> httpx.Client:
    """Synchronous httpx client for Vikunja API."""
    client = httpx.Client(
        base_url="https://tasks.your-domain.com",
        headers={"Authorization": f"Bearer {vikunja_token}"},
        timeout=30.0,
        verify=True,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def faxapi_client(faxapi_base_url) -> httpx.Client:
    """Synchronous httpx client for faxapi."""
    client = httpx.Client(
        base_url=faxapi_base_url,
        timeout=30.0,
    )
    yield client
    client.close()


# ─────────────────────────────────────────────────────────────────────
# Cleanup fixtures (function-scoped)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def inventree_cleanup(inventree_client):
    """Track InvenTree resources created during test; delete them on teardown."""
    created = {
        "stock_items": [],
        "stock_locations": [],
        "parts": [],
        "categories": [],
        "sales_orders": [],
        "companies": [],
    }
    yield created
    # Delete in reverse dependency order
    for item_id in created["stock_items"]:
        inventree_client.delete(f"/api/stock/{item_id}/")
    for item_id in created["sales_orders"]:
        inventree_client.delete(f"/api/order/so/{item_id}/")
    for item_id in created["parts"]:
        inventree_client.delete(f"/api/part/{item_id}/")
    for item_id in created["stock_locations"]:
        inventree_client.delete(f"/api/stock/location/{item_id}/")
    for item_id in created["categories"]:
        inventree_client.delete(f"/api/part/category/{item_id}/")
    for item_id in created["companies"]:
        inventree_client.delete(f"/api/company/{item_id}/")


@pytest.fixture
def vikunja_cleanup(vikunja_client):
    """Track Vikunja resources; delete on teardown."""
    created = {"tasks": [], "projects": []}
    yield created
    for task_id in created["tasks"]:
        vikunja_client.delete(f"/api/v1/tasks/{task_id}")
    for proj_id in created["projects"]:
        vikunja_client.delete(f"/api/v1/projects/{proj_id}")


@pytest.fixture
def faxapi_cleanup(faxapi_client):
    """Track faxapi extensions; delete on teardown."""
    created = {"extensions": []}
    yield created
    for ext in created["extensions"]:
        faxapi_client.delete(f"/extensions/{ext}")
    if created["extensions"]:
        faxapi_client.post("/extensions/reload")


@pytest.fixture
def ldap_cleanup():
    """Track LDAP entries; delete on teardown."""
    import ldap as ldap_lib
    from config import settings

    created_dns = []
    yield created_dns

    if not created_dns:
        return
    try:
        conn = ldap_lib.initialize(settings.ldap_server)
        conn.simple_bind_s(settings.ldap_bind_dn, settings.ldap_bind_password)
        for dn in reversed(created_dns):
            try:
                conn.delete_s(dn)
            except ldap_lib.NO_SUCH_OBJECT:
                pass
        conn.unbind_s()
    except Exception:
        pass

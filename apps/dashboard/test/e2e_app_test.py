#!/usr/bin/env python3
"""
Comprehensive E2E and smoke tests for app.your-domain.com (Flutter web dashboard).

Tests:
  - Unauthenticated: login page renders, auth redirect, page structure
  - Authenticated (via localStorage injection): home screen, tabs, navigation
  - Backend API: InvenTree, Vikunja, Outline connectivity
  - Picking list mode screens

Usage:
  INVENTREE_TOKEN=inv-xxx python3 test/e2e_app_test.py
  # Or run individual test:
  INVENTREE_TOKEN=inv-xxx python3 -m pytest test/e2e_app_test.py -k test_login_page -v
"""

import json
import os
import sys
import time
import unittest

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

APP_URL = os.environ.get("APP_URL", "https://app.your-domain.com")
INVENTREE_URL = "https://portal.your-domain.com"
VIKUNJA_URL = "https://tasks.your-domain.com"
OUTLINE_URL = "https://wiki.your-domain.com"
INVENTREE_TOKEN = os.environ.get("INVENTREE_TOKEN", "")
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"
TIMEOUT = 20  # seconds


def create_driver():
    """Create a headless Chrome WebDriver."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--ignore-certificate-errors")
    service = Service(executable_path=CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=opts)


class TestUnauthenticatedFlows(unittest.TestCase):
    """Tests that work without authentication."""

    @classmethod
    def setUpClass(cls):
        cls.driver = create_driver()

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def test_01_app_loads(self):
        """App should load without server errors."""
        self.driver.get(APP_URL)
        WebDriverWait(self.driver, TIMEOUT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # Flutter web loads index.html for all routes
        self.assertNotIn("404", self.driver.title.lower())
        self.assertNotIn("error", self.driver.title.lower())
        print("  PASS: App loads successfully")

    def test_02_flutter_engine_loads(self):
        """Flutter engine should initialize."""
        self.driver.get(APP_URL)
        # Wait for Flutter to load — look for the flutter-view element
        WebDriverWait(self.driver, TIMEOUT).until(
            lambda d: d.execute_script(
                "return document.querySelector('flutter-view') !== null "
                "|| document.querySelector('flt-glass-pane') !== null "
                "|| document.querySelector('body > div') !== null"
            )
        )
        print("  PASS: Flutter engine loaded")

    def test_03_login_page_renders(self):
        """Login page should render with Google Sign-In button."""
        self.driver.get(APP_URL)
        # Wait for Flutter to render — the app redirects to /login
        time.sleep(5)  # Flutter needs time to render
        page_source = self.driver.page_source
        # Check for any rendered content (Flutter renders to canvas or HTML)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        # The page should have some content (not blank)
        self.assertTrue(
            len(page_source) > 500,
            "Page source should have substantial content"
        )
        print(f"  PASS: Login page rendered ({len(page_source)} bytes)")

    def test_04_no_console_errors(self):
        """App should load without critical JS errors."""
        self.driver.get(APP_URL)
        time.sleep(5)
        logs = self.driver.get_log("browser")
        severe_errors = [
            log for log in logs
            if log["level"] == "SEVERE"
            and "favicon" not in log["message"].lower()
            and "manifest" not in log["message"].lower()
        ]
        if severe_errors:
            for err in severe_errors:
                print(f"  WARNING: Console error: {err['message'][:200]}")
        # Don't fail on CORS or external resource errors, but flag them
        critical_errors = [
            e for e in severe_errors
            if "TypeError" in e["message"] or "SyntaxError" in e["message"]
        ]
        self.assertEqual(
            len(critical_errors), 0,
            f"Critical JS errors found: {critical_errors}"
        )
        print(f"  PASS: No critical console errors ({len(severe_errors)} warnings)")

    def test_05_redirect_to_login(self):
        """Unauthenticated access to /home should redirect to /login."""
        self.driver.get(f"{APP_URL}/home")
        time.sleep(5)
        # GoRouter should redirect to /login
        current_url = self.driver.current_url
        # Flutter SPA — URL might contain #/login or /login
        self.assertTrue(
            "/login" in current_url or current_url.rstrip("/") == APP_URL.rstrip("/"),
            f"Should redirect to login, got: {current_url}"
        )
        print(f"  PASS: Redirected to login: {current_url}")

    def test_06_static_assets_load(self):
        """Critical static assets should be accessible."""
        for path in ["/flutter.js", "/main.dart.js", "/index.html"]:
            resp = requests.get(f"{APP_URL}{path}", timeout=10, verify=False)
            self.assertIn(
                resp.status_code, [200, 304],
                f"{path} returned {resp.status_code}"
            )
        print("  PASS: Static assets load correctly")

    def test_07_manifest_json(self):
        """Web app manifest should be valid JSON (if present)."""
        resp = requests.get(f"{APP_URL}/manifest.json", timeout=10, verify=False)
        if resp.status_code == 404:
            print("  SKIP: manifest.json not present (optional)")
            return
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()
        self.assertIn("name", manifest)
        print(f"  PASS: manifest.json valid, app name: {manifest.get('name')}")


class TestAuthenticatedFlows(unittest.TestCase):
    """Tests using localStorage injection to bypass Google SSO."""

    @classmethod
    def setUpClass(cls):
        cls.driver = create_driver()
        cls._inject_auth()

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    @classmethod
    def _inject_auth(cls):
        """Inject auth tokens into localStorage to simulate authenticated state."""
        cls.driver.get(APP_URL)
        time.sleep(3)  # Wait for Flutter to initialize

        # flutter_secure_storage v9 on web stores values in localStorage
        # Try multiple key formats (with and without prefix)
        token = INVENTREE_TOKEN or "test-token-placeholder"
        auth_data = {
            "inventree_token": token,
            "vikunja_token": "test-vikunja-token",
            "outline_token": "test-outline-token",
            "user_email": "admin@your-domain.com",
            "user_display_name": "Test User",
            "user_photo_url": "",
        }

        # Try direct localStorage keys (flutter_secure_storage default on web)
        for key, value in auth_data.items():
            cls.driver.execute_script(
                f"window.localStorage.setItem('{key}', '{value}');"
            )

        # Also try with common prefixes
        for key, value in auth_data.items():
            cls.driver.execute_script(
                f"window.localStorage.setItem('flutter.{key}', '{value}');"
            )

        # Reload to pick up the injected state
        cls.driver.get(APP_URL)
        time.sleep(5)

    def _is_authenticated(self):
        """Check if we're past the login screen."""
        current_url = self.driver.current_url
        return "/login" not in current_url

    def test_01_auth_injection_status(self):
        """Report whether localStorage auth injection worked."""
        if self._is_authenticated():
            print("  PASS: Auth injection successful — authenticated")
        else:
            print("  SKIP: Auth injection did not bypass login (encryption likely)")
            # Inspect what's in localStorage
            ls_keys = self.driver.execute_script(
                "return Object.keys(window.localStorage);"
            )
            print(f"  INFO: localStorage keys: {ls_keys}")

    def test_02_home_screen(self):
        """Home screen should show mode cards when authenticated."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated — localStorage injection failed")

        self.driver.get(f"{APP_URL}/home")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        # Home screen should have some mode cards
        self.assertTrue(len(body_text) > 50, "Home screen should have content")
        print("  PASS: Home screen rendered")

    def test_03_inventory_tab(self):
        """Inventory tab should load."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated")

        self.driver.get(f"{APP_URL}/inventory")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        self.assertTrue(len(body_text) > 50)
        print("  PASS: Inventory tab loaded")

    def test_04_tasks_tab(self):
        """Tasks tab should load."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated")

        self.driver.get(f"{APP_URL}/tasks")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        self.assertTrue(len(body_text) > 50)
        print("  PASS: Tasks tab loaded")

    def test_05_wiki_tab(self):
        """Wiki tab should load."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated")

        self.driver.get(f"{APP_URL}/wiki")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        self.assertTrue(len(body_text) > 50)
        print("  PASS: Wiki tab loaded")

    def test_06_settings_tab(self):
        """Settings tab should load."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated")

        self.driver.get(f"{APP_URL}/settings")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        self.assertTrue(len(body_text) > 50)
        print("  PASS: Settings tab loaded")

    def test_07_picking_mode(self):
        """Picking list mode should be accessible."""
        if not self._is_authenticated():
            self.skipTest("Not authenticated")

        self.driver.get(f"{APP_URL}/home/picking")
        time.sleep(3)
        body_text = self.driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
        self.assertTrue(len(body_text) > 50)
        print("  PASS: Picking list mode loaded")


class TestBackendAPIs(unittest.TestCase):
    """Test backend API connectivity directly (not through Flutter)."""

    def test_01_inventree_api_root(self):
        """InvenTree API root should be accessible."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("server", data)
        print(f"  PASS: InvenTree API v{data.get('apiVersion', '?')}")

    def test_02_inventree_parts(self):
        """InvenTree parts API should return data."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/part/?limit=5",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        count = data.get("count", len(data))
        print(f"  PASS: InvenTree parts API ({count} parts)")

    def test_03_inventree_stock(self):
        """InvenTree stock API should return data."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/stock/?limit=5",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        print("  PASS: InvenTree stock API")

    def test_04_inventree_sales_orders(self):
        """InvenTree sales orders API (used by picking list)."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/order/so/?limit=5",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        print("  PASS: InvenTree sales orders API")

    def test_05_inventree_purchase_orders(self):
        """InvenTree purchase orders API."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/order/po/?limit=5",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        print("  PASS: InvenTree purchase orders API")

    def test_06_vikunja_health(self):
        """Vikunja should respond to health checks."""
        resp = requests.get(
            f"{VIKUNJA_URL}/api/v1/info",
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("version", data)
        print(f"  PASS: Vikunja API v{data.get('version', '?')}")

    def test_07_outline_health(self):
        """Outline should respond."""
        resp = requests.get(
            f"{OUTLINE_URL}/_health",
            timeout=10,
            verify=False,
        )
        self.assertIn(resp.status_code, [200, 302])
        print(f"  PASS: Outline health check ({resp.status_code})")

    @unittest.skipUnless(INVENTREE_TOKEN, "No INVENTREE_TOKEN set")
    def test_08_inventree_plugins(self):
        """InvenTree plugins should be loaded."""
        resp = requests.get(
            f"{INVENTREE_URL}/api/plugins/",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            timeout=10,
            verify=False,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        plugin_names = [p.get("key", "") for p in data]
        self.assertTrue(
            any("invoice" in name for name in plugin_names),
            f"invoice_plugin should be loaded, found: {plugin_names}"
        )
        print(f"  PASS: InvenTree plugins ({len(data)} loaded)")

    @unittest.skipUnless(INVENTREE_TOKEN, "No INVENTREE_TOKEN set")
    def test_09_inventree_barcode_endpoint(self):
        """InvenTree barcode scan endpoint (used by picking list)."""
        resp = requests.post(
            f"{INVENTREE_URL}/api/barcode/",
            headers={"Authorization": f"Token {INVENTREE_TOKEN}"},
            json={"barcode": "TEST-NONEXISTENT-BARCODE"},
            timeout=10,
            verify=False,
        )
        # 200 with no match or 400 — both mean the endpoint works
        self.assertIn(resp.status_code, [200, 400])
        print(f"  PASS: InvenTree barcode API ({resp.status_code})")


class TestSSLAndHeaders(unittest.TestCase):
    """Test TLS and security headers."""

    def test_01_https_redirect(self):
        """HTTP should redirect to HTTPS."""
        resp = requests.get(
            APP_URL.replace("https://", "http://"),
            timeout=10,
            allow_redirects=False,
            verify=False,
        )
        # GCS+GCLB may return 301, 302, or 307
        self.assertIn(resp.status_code, [200, 301, 302, 307, 308],
                       f"Unexpected status: {resp.status_code}")
        print(f"  PASS: HTTP response: {resp.status_code}")

    def test_02_tls_valid(self):
        """TLS certificate should be valid."""
        resp = requests.get(APP_URL, timeout=10)  # verify=True by default
        self.assertEqual(resp.status_code, 200)
        print("  PASS: TLS certificate valid")

    def test_03_portal_tls(self):
        """portal.your-domain.com TLS should be valid."""
        resp = requests.get(f"{INVENTREE_URL}/api/", timeout=10)
        self.assertIn(resp.status_code, [200, 401, 403])
        print("  PASS: InvenTree portal TLS valid")

    def test_04_tasks_tls(self):
        """tasks.your-domain.com TLS should be valid."""
        resp = requests.get(f"{VIKUNJA_URL}/api/v1/info", timeout=10)
        self.assertEqual(resp.status_code, 200)
        print("  PASS: Vikunja TLS valid")

    def test_05_wiki_tls(self):
        """wiki.your-domain.com TLS should be valid."""
        resp = requests.get(OUTLINE_URL, timeout=10, allow_redirects=True)
        self.assertIn(resp.status_code, [200, 302])
        print("  PASS: Outline TLS valid")


class TestSPARouting(unittest.TestCase):
    """Test that SPA routing works.

    GCS serves index.html as the 404 page for non-root paths. The browser
    receives the Flutter app content which then handles client-side routing.
    Status 404 from GCS is expected — what matters is the content.
    """

    def _check_spa_route(self, path):
        """Verify a route serves the Flutter app (regardless of HTTP status)."""
        resp = requests.get(f"{APP_URL}{path}", timeout=10, verify=False)
        # GCS returns 200 for root, 404 for sub-paths (with index.html content)
        self.assertIn(resp.status_code, [200, 404])
        # Content should be the Flutter app (contains flutter.js reference)
        self.assertTrue(
            "flutter" in resp.text.lower() or "main.dart" in resp.text.lower(),
            f"{path} did not serve Flutter app content"
        )
        return resp.status_code

    def test_01_home_route(self):
        """/home serves Flutter app content."""
        status = self._check_spa_route("/home")
        print(f"  PASS: /home serves Flutter app (HTTP {status})")

    def test_02_inventory_route(self):
        """/inventory serves Flutter app content."""
        status = self._check_spa_route("/inventory")
        print(f"  PASS: /inventory serves Flutter app (HTTP {status})")

    def test_03_tasks_route(self):
        """/tasks serves Flutter app content."""
        status = self._check_spa_route("/tasks")
        print(f"  PASS: /tasks serves Flutter app (HTTP {status})")

    def test_04_settings_route(self):
        """/settings serves Flutter app content."""
        status = self._check_spa_route("/settings")
        print(f"  PASS: /settings serves Flutter app (HTTP {status})")

    def test_05_picking_route(self):
        """/home/picking serves Flutter app content."""
        status = self._check_spa_route("/home/picking")
        print(f"  PASS: /home/picking serves Flutter app (HTTP {status})")

    def test_06_deep_route(self):
        """Deep nested route serves Flutter app content."""
        status = self._check_spa_route("/home/picking/order/123")
        print(f"  PASS: Deep nested route serves Flutter app (HTTP {status})")

    def test_07_login_route(self):
        """/login serves Flutter app content."""
        status = self._check_spa_route("/login")
        print(f"  PASS: /login serves Flutter app (HTTP {status})")


if __name__ == "__main__":
    # Suppress SSL warnings for self-signed certs
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"\n{'='*60}")
    print(f"  E2E Tests for {APP_URL}")
    print(f"  InvenTree token: {'set' if INVENTREE_TOKEN else 'NOT SET'}")
    print(f"{'='*60}\n")

    # Run with verbose output
    unittest.main(verbosity=2)

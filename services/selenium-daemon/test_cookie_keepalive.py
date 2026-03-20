"""Test cookie persistence: login, save cookies, close, restore, verify."""

import asyncio
import json
import os
import sys

os.environ.setdefault("CONFIG_PATH", "/home/pi/SHINBEE/config.yaml")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:8200")
os.environ.setdefault("VAULT_APPROLE_ROLE_ID_PATH", "/root/vault-approle-admin-role-id")
os.environ.setdefault("VAULT_APPROLE_SECRET_ID_PATH", "/root/vault-approle-admin-secret-id")
os.environ.setdefault("DISPLAY", ":99")

import nodriver as uc
from daemon.vault_client import VaultClient
from daemon import config as cfg

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_COOKIE_DIR = "/tmp/login_inspect"


async def _start_browser():
    return await uc.start(
        headless=False,
        browser_args=[
            "--no-sandbox",
            "--window-size=1920,1080",
            f"--user-agent={_UA}",
        ],
    )


async def _save_cookies(page, name):
    """Save all browser cookies via CDP."""
    result = await page.send(uc.cdp.network.get_cookies())
    cookies = []
    for c in result:
        entry = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": c.secure,
            "httpOnly": c.http_only,
        }
        if c.same_site is not None:
            entry["sameSite"] = c.same_site.value
        if c.expires is not None and c.expires > 0:
            entry["expires"] = int(c.expires)
        cookies.append(entry)

    path = f"{_COOKIE_DIR}/{name}_cookies.json"
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Saved {len(cookies)} cookies to {path}")
    return cookies


async def _inject_cookies(page, name):
    """Inject saved cookies into a fresh browser via CDP."""
    path = f"{_COOKIE_DIR}/{name}_cookies.json"
    with open(path) as f:
        cookies = json.load(f)

    _ss_map = {
        "Strict": uc.cdp.network.CookieSameSite.STRICT,
        "Lax": uc.cdp.network.CookieSameSite.LAX,
        "None": uc.cdp.network.CookieSameSite.NONE,
    }
    ok = 0
    for cookie in cookies:
        try:
            params = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                params["secure"] = True
            if cookie.get("httpOnly"):
                params["http_only"] = True
            if cookie.get("sameSite"):
                ss_val = _ss_map.get(cookie["sameSite"])
                if ss_val is not None:
                    params["same_site"] = ss_val
            if cookie.get("expires"):
                params["expires"] = uc.cdp.network.TimeSinceEpoch(
                    float(cookie["expires"])
                )
            await page.send(uc.cdp.network.set_cookie(**params))
            ok += 1
        except Exception as e:
            print(f"  Warning: failed to set cookie {cookie.get('name')}: {e}")
    print(f"  Successfully set {ok}/{len(cookies)} cookies")

    print(f"  Injected {len(cookies)} cookies")


async def test_yamato_keepalive(vault):
    print("\n=== Yamato Cookie Keep-Alive Test ===")
    creds = vault.read("daemon/yamato")
    login_url = cfg.cfg("daemon.sessions.yamato.login_url")

    # --- Phase 1: Login and save cookies ---
    print("\n[Phase 1] Login and save cookies")
    browser = await _start_browser()
    page = await browser.get(login_url)
    await asyncio.sleep(4)

    code1 = await page.find("#code1", timeout=5)
    await code1.click()
    await asyncio.sleep(0.3)
    await code1.send_keys(creds["login_id"])

    pw = await page.find("#password", timeout=5)
    await pw.click()
    await asyncio.sleep(0.3)
    await pw.send_keys(creds["password"])

    login_btn = await page.find("a.login", timeout=5)
    await login_btn.click()
    await asyncio.sleep(6)

    url = page.url
    print(f"  Post-login URL: {url}")
    logged_in = "LOGGEDIN" in url or "servlet" in url
    print(f"  Login success: {logged_in}")

    if not logged_in:
        browser.stop()
        return False

    await _save_cookies(page, "yamato")
    browser.stop()
    print("  Browser closed.")
    await asyncio.sleep(2)

    # --- Phase 2: New browser, inject cookies, verify ---
    print("\n[Phase 2] Restore cookies in fresh browser")
    browser2 = await _start_browser()
    page2 = await browser2.get("about:blank")
    await _inject_cookies(page2, "yamato")

    # Navigate to Yamato with cookies
    page2 = await browser2.get(login_url)
    await asyncio.sleep(5)

    url2 = page2.url
    title2 = await page2.evaluate("document.title")
    print(f"  URL after cookie restore: {url2}")
    print(f"  Title: {title2}")
    await page2.save_screenshot(f"{_COOKIE_DIR}/yamato_keepalive.png")

    # Check if we're on the dashboard (not the login form)
    has_login_form = await page2.evaluate(
        "!!document.querySelector('#code1')"
    )
    print(f"  Login form visible: {has_login_form}")
    print(f"  Keep-alive SUCCESS: {not has_login_form}")

    browser2.stop()
    return not has_login_form


async def test_sagawa_keepalive(vault):
    print("\n=== Sagawa Cookie Keep-Alive Test ===")
    creds = vault.read("daemon/sagawa")
    login_url = cfg.cfg("daemon.sessions.sagawa.login_url")

    # --- Phase 1: Login and save cookies ---
    print("\n[Phase 1] Login and save cookies")
    browser = await _start_browser()
    page = await browser.get(login_url)
    await asyncio.sleep(6)

    title = await page.evaluate("document.title")
    if "Access Denied" in (title or ""):
        print("  ERROR: Akamai blocked access")
        browser.stop()
        return False

    # Click business tab
    biz_tab = await page.find("#tab02", timeout=5)
    if biz_tab:
        await biz_tab.click()
        await asyncio.sleep(1)

    user_el = await page.find("#user2", timeout=5)
    await user_el.click()
    await asyncio.sleep(0.3)
    await user_el.send_keys(creds["user_id"])

    pw_el = await page.find("#pass2", timeout=5)
    await pw_el.click()
    await asyncio.sleep(0.3)
    await pw_el.send_keys(creds["password"])

    login_btn = await page.find("#hojin-login-button", timeout=5)
    await login_btn.click()
    await asyncio.sleep(8)

    url = page.url
    title = await page.evaluate("document.title")
    print(f"  Post-login URL: {url}")
    print(f"  Title: {title}")
    logged_in = "spastart" in url or "メニュー" in (title or "")
    print(f"  Login success: {logged_in}")

    if not logged_in:
        browser.stop()
        return False

    await _save_cookies(page, "sagawa")
    browser.stop()
    print("  Browser closed.")
    await asyncio.sleep(2)

    # --- Phase 2: New browser, inject cookies, verify ---
    print("\n[Phase 2] Restore cookies in fresh browser")
    browser2 = await _start_browser()
    page2 = await browser2.get("about:blank")
    await _inject_cookies(page2, "sagawa")

    # Navigate to Sagawa with cookies
    page2 = await browser2.get(login_url)
    await asyncio.sleep(8)

    url2 = page2.url
    title2 = await page2.evaluate("document.title")
    print(f"  URL after cookie restore: {url2}")
    print(f"  Title: {title2}")
    await page2.save_screenshot(f"{_COOKIE_DIR}/sagawa_keepalive.png")

    # Check if we're on the dashboard (not the login form)
    on_menu = "メニュー" in (title2 or "") or "spastart" in url2
    has_login = "auth/realms" in url2
    print(f"  On dashboard: {on_menu}")
    print(f"  On login page: {has_login}")
    print(f"  Keep-alive SUCCESS: {on_menu}")

    browser2.stop()
    return on_menu


async def main():
    vault = VaultClient()
    target = sys.argv[1] if len(sys.argv) > 1 else "both"

    results = {}
    if target in ("yamato", "both"):
        results["yamato"] = await test_yamato_keepalive(vault)
    if target in ("sagawa", "both"):
        results["sagawa"] = await test_sagawa_keepalive(vault)

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())

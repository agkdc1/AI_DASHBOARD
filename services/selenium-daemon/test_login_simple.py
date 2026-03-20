"""Minimal login test — bypasses Gemini page analysis, just screenshots."""

import asyncio
import os
import sys

os.environ.setdefault("CONFIG_PATH", "/home/pi/SHINBEE/config.yaml")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:8200")
os.environ.setdefault("VAULT_APPROLE_ROLE_ID_PATH", "/root/vault-approle-admin-role-id")
os.environ.setdefault("VAULT_APPROLE_SECRET_ID_PATH", "/root/vault-approle-admin-secret-id")

import random
import nodriver as uc
from daemon.vault_client import VaultClient
from daemon import config as cfg

# Ensure DISPLAY for non-headless mode (Xvfb)
os.environ.setdefault("DISPLAY", ":99")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def test_yamato(vault):
    print("\n=== Yamato Login Test ===")
    creds = vault.read("daemon/yamato")
    login_url = cfg.cfg("daemon.sessions.yamato.login_url")
    print(f"URL: {login_url}")
    print(f"Fields: {list(creds.keys())}")

    browser = await uc.start(headless=False, browser_args=["--no-sandbox", "--window-size=1920,1080", f"--user-agent={_UA}"])
    page = await browser.get(login_url)
    await asyncio.sleep(4)
    await page.save_screenshot("/tmp/login_inspect/yamato_01_loaded.png")
    print("Screenshot: yamato_01_loaded.png")

    # Fill customer code
    code1 = await page.find("#code1", timeout=5)
    if code1:
        await code1.click()
        await asyncio.sleep(0.3)
        await code1.send_keys(creds["login_id"])
        await asyncio.sleep(0.5)
        print(f"Filled code1")
    else:
        print("ERROR: #code1 not found")

    # Fill password
    pw = await page.find("#password", timeout=5)
    if pw:
        await pw.click()
        await asyncio.sleep(0.3)
        await pw.send_keys(creds["password"])
        await asyncio.sleep(0.5)
        print(f"Filled password")
    else:
        print("ERROR: #password not found")

    await page.save_screenshot("/tmp/login_inspect/yamato_02_filled.png")
    print("Screenshot: yamato_02_filled.png")

    # Click login
    login_btn = await page.find("a.login", timeout=5)
    if login_btn:
        await login_btn.click()
        print("Clicked login button")
        await asyncio.sleep(6)
    else:
        print("ERROR: a.login not found")

    await page.save_screenshot("/tmp/login_inspect/yamato_03_after_login.png")
    print("Screenshot: yamato_03_after_login.png")

    # Check URL
    url = page.url
    print(f"Current URL: {url}")

    browser.stop()


async def test_sagawa(vault):
    print("\n=== Sagawa Login Test ===")
    creds = vault.read("daemon/sagawa")
    login_url = cfg.cfg("daemon.sessions.sagawa.login_url")
    print(f"URL: {login_url}")
    print(f"Fields: {list(creds.keys())}")

    browser = await uc.start(
        headless=False,
        browser_args=[
            "--no-sandbox",
            "--window-size=1920,1080",
            "--lang=ja-JP,ja,en-US,en",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ],
    )
    page = await browser.get(login_url)
    await asyncio.sleep(6)
    await page.save_screenshot("/tmp/login_inspect/sagawa_01_loaded.png")
    print("Screenshot: sagawa_01_loaded.png")
    print(f"Current URL: {page.url}")

    # Check if we got Access Denied
    title = await page.evaluate("document.title")
    print(f"Page title: {title}")
    if "Access Denied" in (title or ""):
        print("ERROR: Akamai blocked access. Stopping.")
        browser.stop()
        return

    # Click 法人 (business) tab
    biz_tab = await page.find("#tab02", timeout=5)
    if biz_tab:
        await biz_tab.click()
        await asyncio.sleep(1)
        print("Clicked business tab")
    else:
        print("ERROR: #tab02 (business tab) not found")

    await page.save_screenshot("/tmp/login_inspect/sagawa_02_biz_tab.png")
    print("Screenshot: sagawa_02_biz_tab.png")

    # Fill user ID (phone number + 3 digits)
    user_el = await page.find("#user2", timeout=5)
    if user_el:
        await user_el.click()
        await asyncio.sleep(0.3)
        await user_el.send_keys(creds["user_id"])
        await asyncio.sleep(0.5)
        print("Filled user2")
    else:
        print("ERROR: #user2 not found")

    # Fill password
    pw_el = await page.find("#pass2", timeout=5)
    if pw_el:
        await pw_el.click()
        await asyncio.sleep(0.3)
        await pw_el.send_keys(creds["password"])
        await asyncio.sleep(0.5)
        print("Filled pass2")
    else:
        print("ERROR: #pass2 not found")

    await page.save_screenshot("/tmp/login_inspect/sagawa_03_filled.png")
    print("Screenshot: sagawa_03_filled.png")

    # Click login button
    login_btn = await page.find("#hojin-login-button", timeout=5)
    if login_btn:
        await login_btn.click()
        print("Clicked hojin-login-button")
        await asyncio.sleep(8)
    else:
        print("ERROR: #hojin-login-button not found")

    await page.save_screenshot("/tmp/login_inspect/sagawa_04_after_login.png")
    print("Screenshot: sagawa_04_after_login.png")

    # Check URL
    url = page.url
    print(f"Current URL: {url}")
    title = await page.evaluate("document.title")
    print(f"Page title: {title}")

    browser.stop()


async def main():
    vault = VaultClient()
    target = sys.argv[1] if len(sys.argv) > 1 else "both"

    if target in ("yamato", "both"):
        await test_yamato(vault)
    if target in ("sagawa", "both"):
        await test_sagawa(vault)


if __name__ == "__main__":
    asyncio.run(main())

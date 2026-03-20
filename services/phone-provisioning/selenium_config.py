#!/usr/bin/env python3
"""Configure Grandstream GXP-1760W phones via Selenium (web GUI).

The HTTP API (api.values.post) does not reliably persist all P-codes —
in particular P8468 (Public Mode) reverts after reboot on some firmware.
The web GUI uses GWT form names (e.g. P1345 for Public Mode) which
persist correctly through save+reboot.

Usage:
    python3 phone/selenium_config.py                          # all hot-desk phones
    python3 phone/selenium_config.py --ip 10.0.7.12           # single phone
    python3 phone/selenium_config.py --type fixed              # only fixed phones
    python3 phone/selenium_config.py --dry-run                 # read-only check
    python3 phone/selenium_config.py --ip 10.0.7.12 --check   # just verify settings
"""

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

import yaml

GRANDSTREAM_OUI = "c0:74:ad"
CHROMIUM_BIN = "/usr/bin/chromium"
CHROMEDRIVER_BIN = "/usr/bin/chromedriver"
LOGIN_WAIT = 4
PAGE_WAIT = 4


# ── Config loading ─────────────────────────────────────────────────
def load_config(repo_root: Path) -> dict:
    with open(repo_root / "config.yaml") as f:
        return yaml.safe_load(f)


def mac_normalize(mac: str) -> str:
    return re.sub(r"[:\-.]", "", mac).lower().zfill(12)


def wifi_mac_to_eth(wifi_mac: str) -> str:
    clean = re.sub(r"[:\-.]", "", wifi_mac).lower().zfill(12)
    return f"{int(clean, 16) - 1:012x}"


def discover_phones() -> dict[str, str]:
    result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    phones = {}
    for line in result.stdout.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([\da-f:]+)", line)
        if m:
            ip, mac = m.group(1), m.group(2)
            if mac.startswith(GRANDSTREAM_OUI):
                phones[ip] = mac
    return phones


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_phone_lookup(repo_root: Path, cfg: dict) -> dict:
    phone = cfg["phone"]
    lookup = {}
    for row in read_csv(repo_root / phone["csv_fixed"]):
        eth = mac_normalize(row["MAC"])
        lookup[eth] = {"type": "fixed", "ext": row["NUMBER"], "name": row["NAME"]}
    for row in read_csv(repo_root / phone["csv_free_phones"]):
        eth = mac_normalize(row["MAC"])
        lookup[eth] = {"type": "hotdesk", "ext": "", "name": "hot-desk"}
    return lookup


# ── Selenium driver ────────────────────────────────────────────────
def make_driver():
    opts = Options()
    opts.binary_location = CHROMIUM_BIN
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    svc = Service(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(30)
    return driver


def gs_login(driver, ip: str, password: str) -> bool:
    """Login to Grandstream web GUI. Returns True on success."""
    driver.get(f"http://{ip}")
    time.sleep(LOGIN_WAIT)
    try:
        driver.find_element(By.CSS_SELECTOR, "input.gwt-TextBox").send_keys("admin")
        driver.find_element(By.CSS_SELECTOR, "input.gwt-PasswordTextBox").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button.gwt-Button").click()
        time.sleep(LOGIN_WAIT)
        return "status" in driver.current_url or "page:" in driver.current_url
    except Exception as e:
        print(f"    Login error: {e}")
        return False


def gs_navigate(driver, ip: str, page: str):
    """Navigate to a GWT page by hash fragment."""
    driver.get(f"http://{ip}/#{page}")
    time.sleep(PAGE_WAIT)


def gs_read_radio(driver, gwt_form_name: str) -> str | None:
    """Read current value of a GWT radio button group by form name attribute."""
    return driver.execute_script(f"""
        var radios = document.querySelectorAll('input[name="{gwt_form_name}"]');
        for (var i = 0; i < radios.length; i++) {{
            if (radios[i].checked) return radios[i].value;
        }}
        return null;
    """)


def gs_set_radio(driver, gwt_form_name: str, value: str) -> bool:
    """Set a GWT radio button by form name and value. Returns True if changed."""
    return driver.execute_script(f"""
        var radios = document.querySelectorAll('input[name="{gwt_form_name}"]');
        for (var i = 0; i < radios.length; i++) {{
            if (radios[i].value === "{value}") {{
                if (radios[i].checked) return false;  // already set
                radios[i].click();
                return true;
            }}
        }}
        return false;
    """)


def gs_read_input(driver, gwt_form_name: str) -> str | None:
    """Read a GWT text input value by name."""
    return driver.execute_script(f"""
        var el = document.querySelector('input[name="{gwt_form_name}"]');
        return el ? el.value : null;
    """)


def gs_set_input(driver, gwt_form_name: str, value: str) -> bool:
    """Set a GWT text input by name. Returns True if changed."""
    return driver.execute_script(f"""
        var el = document.querySelector('input[name="{gwt_form_name}"]');
        if (!el) return false;
        if (el.value === "{value}") return false;
        // Use native setter to trigger GWT change events
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(el, "{value}");
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true;
    """)


def gs_save_and_apply(driver) -> bool:
    """Click 'Save and Apply' button."""
    try:
        btns = driver.find_elements(By.XPATH, "//*[contains(text(),'Save and Apply')]")
        if btns:
            btns[0].click()
            time.sleep(5)
            # Handle any confirmation dialog
            try:
                alert = driver.switch_to.alert
                alert.accept()
                time.sleep(2)
            except Exception:
                pass
            return True
    except Exception as e:
        print(f"    Save error: {e}")
    return False


def gs_get_model_info(driver, ip: str) -> dict:
    """Read model, firmware, MAC from status page."""
    gs_navigate(driver, ip, "page:status_account")
    text = driver.find_element(By.TAG_NAME, "body").text
    info = {"model": "?", "firmware": "?"}
    m = re.search(r"(GXP\w+)", text)
    if m:
        info["model"] = m.group(1)
    m = re.search(r"Version\s+([\d.]+)", text)
    if m:
        info["firmware"] = m.group(1)
    return info


# ── GWT form name mappings ─────────────────────────────────────────
# These are the GWT form names used in the web GUI (NOT the same as
# the P-codes used by api.values.post). Discovered by inspecting the
# Grandstream GWT page DOM.
#
# Page: settings_general
GWT_PUBLIC_MODE = "P1345"       # API P8468: Public Mode (0=No, 1=Yes)

# Page: account1 (SIP Account 1 settings)
# These need to be discovered per-page — TBD in future iterations.
# For now, the critical fix is Public Mode via settings_general.


# ── Phone configuration workflows ─────────────────────────────────
def check_phone(driver, ip: str) -> dict:
    """Read current settings from a phone. Returns dict of settings."""
    settings = {}
    gs_navigate(driver, ip, "page:settings_general")
    settings["public_mode"] = gs_read_radio(driver, GWT_PUBLIC_MODE)
    return settings


def configure_hotdesk(driver, ip: str) -> tuple[bool, list[str]]:
    """Configure a hot-desk phone via web GUI. Returns (changed, changes_list).

    Hot-desk phones use CFU-based seating (Flutter check-in sets call forwarding).
    Public Mode must be OFF so the phone auto-registers with its permanent desk
    extension instead of waiting for manual handset login.
    """
    changes = []

    # Settings > General: Public Mode = No (CFU seating — phone keeps permanent desk ext)
    gs_navigate(driver, ip, "page:settings_general")
    current = gs_read_radio(driver, GWT_PUBLIC_MODE)
    if current != "0":
        if gs_set_radio(driver, GWT_PUBLIC_MODE, "0"):
            changes.append(f"Public Mode: {current} → 0")
            gs_save_and_apply(driver)
        else:
            print(f"    WARNING: Could not set Public Mode radio")

    return len(changes) > 0, changes


def configure_fixed(driver, ip: str, ext: str) -> tuple[bool, list[str]]:
    """Configure a fixed phone via web GUI. Returns (changed, changes_list)."""
    changes = []

    # Settings > General: Public Mode = No (fixed phones must not have public mode)
    gs_navigate(driver, ip, "page:settings_general")
    current = gs_read_radio(driver, GWT_PUBLIC_MODE)
    if current != "0":
        if gs_set_radio(driver, GWT_PUBLIC_MODE, "0"):
            changes.append(f"Public Mode: {current} → 0")
            gs_save_and_apply(driver)

    return len(changes) > 0, changes


# ── Main ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Configure Grandstream phones via Selenium web GUI")
    parser.add_argument("--ip", help="Target a single phone IP")
    parser.add_argument("--type", choices=["fixed", "hotdesk"],
                        help="Only configure this phone type")
    parser.add_argument("--dry-run", action="store_true",
                        help="Read-only: show current settings without changing")
    parser.add_argument("--check", action="store_true",
                        help="Alias for --dry-run")
    args = parser.parse_args()

    if args.check:
        args.dry_run = True

    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_config(repo_root)
    phone_cfg = cfg["phone"]
    admin_pw = phone_cfg["admin_password"]

    phone_lookup = build_phone_lookup(repo_root, cfg)

    if args.ip:
        phones = {args.ip: "manual"}
    else:
        phones = discover_phones()
        if not phones:
            print("No Grandstream phones found in ARP table.")
            sys.exit(1)

    print(f"Found {len(phones)} phone(s)\n")

    ok_count = 0
    change_count = 0
    fail_count = 0

    for ip, wifi_mac in sorted(phones.items()):
        eth_mac = wifi_mac_to_eth(wifi_mac) if wifi_mac != "manual" else "unknown"
        info = phone_lookup.get(eth_mac, {"type": "unknown", "ext": "?", "name": "?"})

        if args.type and info["type"] != args.type:
            continue

        label = f"{ip} [{info['type']}]"
        if info["type"] == "fixed":
            label += f" ext={info['ext']} ({info['name']})"

        print(f"  {label}")

        driver = make_driver()
        try:
            if not gs_login(driver, ip, admin_pw):
                print(f"    FAILED to login")
                fail_count += 1
                continue

            # Read current settings
            settings = check_phone(driver, ip)
            pm_display = "Yes" if settings["public_mode"] == "1" else "No"
            print(f"    Public Mode = {pm_display} (GWT {GWT_PUBLIC_MODE}={settings['public_mode']})")

            if args.dry_run:
                ok_count += 1
                continue

            # Configure based on type
            if info["type"] == "hotdesk" or info["type"] == "unknown":
                changed, changes = configure_hotdesk(driver, ip)
            elif info["type"] == "fixed":
                changed, changes = configure_fixed(driver, ip, info["ext"])
            else:
                changed, changes = False, []

            if changed:
                for c in changes:
                    print(f"    CHANGED: {c}")
                change_count += 1

                # Re-read to verify
                settings = check_phone(driver, ip)
                pm_verify = "Yes" if settings["public_mode"] == "1" else "No"
                print(f"    Verified: Public Mode = {pm_verify}")
            else:
                print(f"    OK (no changes needed)")

            ok_count += 1

        except Exception as e:
            print(f"    ERROR: {e}")
            fail_count += 1
        finally:
            driver.quit()

    print(f"\nDone: {ok_count} OK, {change_count} changed, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

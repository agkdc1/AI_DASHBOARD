"""Inspect login pages for Yamato and Sagawa — capture screenshots + HTML."""

import asyncio
import os
import sys

os.environ.setdefault("CONFIG_PATH", "/home/pi/SHINBEE/config.yaml")

import nodriver as uc


async def inspect(name, url, out_dir="/tmp/login_inspect"):
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n[{name}] Launching browser...")
    browser = await uc.start(
        headless=True,
        browser_args=[
            "--no-sandbox",
            "--disable-gpu",
            "--window-size=1920,1080",
        ],
    )

    page = await browser.get(url)
    await asyncio.sleep(5)

    # Screenshot
    ss_path = f"{out_dir}/{name}_login.png"
    await page.save_screenshot(ss_path)
    print(f"[{name}] Screenshot saved: {ss_path}")

    # Dump HTML of input fields and buttons
    html = await page.evaluate("""
        (() => {
            const els = document.querySelectorAll('input, button, select, a[type="submit"], [role="button"]');
            return Array.from(els).map(el => {
                return {
                    tag: el.tagName,
                    type: el.type || '',
                    id: el.id || '',
                    name: el.name || '',
                    class: el.className || '',
                    placeholder: el.placeholder || '',
                    value: el.type === 'submit' ? el.value : '',
                    text: el.textContent?.trim()?.substring(0, 50) || '',
                    outerHTML: el.outerHTML.substring(0, 300),
                };
            });
        })()
    """)

    html_path = f"{out_dir}/{name}_fields.txt"
    with open(html_path, "w") as f:
        for item in html:
            f.write(f"--- {item.get('tag', '?')} ---\n")
            for k, v in item.items():
                if v:
                    f.write(f"  {k}: {v}\n")
            f.write("\n")
    print(f"[{name}] Form fields saved: {html_path}")

    # Also dump full page source
    src = await page.evaluate("document.documentElement.outerHTML")
    src_path = f"{out_dir}/{name}_source.html"
    with open(src_path, "w") as f:
        f.write(src)
    print(f"[{name}] Page source saved: {src_path}")

    browser.stop()
    print(f"[{name}] Done")


async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "both"

    if target in ("yamato", "both"):
        await inspect("yamato", "https://bmypage.kuronekoyamato.co.jp/")

    if target in ("sagawa", "both"):
        await inspect(
            "sagawa",
            "https://www.e-service.sagawa-exp.co.jp/",
        )


if __name__ == "__main__":
    asyncio.run(main())

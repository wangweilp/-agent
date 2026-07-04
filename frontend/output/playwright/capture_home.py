import json
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3100"
PHASE = sys.argv[2] if len(sys.argv) > 2 else "before"
OUT_DIR = Path(__file__).resolve().parent

VIEWPORTS = [
    ("375x812", 375, 812),
    ("768x1024", 768, 1024),
    ("1440x900", 1440, 900),
    ("1920x1080", 1920, 1080),
]

AUTH_STATE = {
    "state": {
        "token": {
            "access_token": "visual-audit-token",
            "refresh_token": "visual-audit-refresh",
            "token_type": "Bearer",
        },
        "user": {
            "id": "visual-audit-user",
            "email": "designer@zhiwei.local",
            "name": "Design Audit",
            "role": "Product",
        },
        "currentWorkspace": {
            "id": "visual-audit-workspace",
            "name": "Enterprise Cognitive Workspace",
            "role": "owner",
        },
    },
    "version": 0,
}


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--proxy-server=direct://", "--proxy-bypass-list=*"],
        )
        for label, width, height in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_default_timeout(60000)
            console_messages = []
            page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
            page.on("pageerror", lambda exc: console_messages.append(f"pageerror: {exc}"))
            page.goto(BASE_URL + "/login", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            page.evaluate(
                "(value) => localStorage.setItem('agent-os-auth', value)",
                json.dumps(AUTH_STATE),
            )
            page.goto(BASE_URL + "/home", wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                console_messages.append("warning: networkidle timeout; continuing after domcontentloaded")
            page.wait_for_timeout(600)

            screenshot_path = OUT_DIR / f"{PHASE}-home-{label}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)

            metrics = page.evaluate(
                """() => ({
                    url: location.href,
                    bodyScrollWidth: document.body.scrollWidth,
                    bodyClientWidth: document.body.clientWidth,
                    docScrollWidth: document.documentElement.scrollWidth,
                    docClientWidth: document.documentElement.clientWidth,
                    title: document.querySelector('h1')?.innerText || '',
                    headerText: document.querySelector('header')?.innerText || '',
                    cards: Array.from(document.querySelectorAll('article h3')).map((el) => el.textContent),
                })"""
            )
            metrics["screenshot"] = str(screenshot_path)
            metrics["viewport"] = label
            metrics["console"] = console_messages[-20:]
            results.append(metrics)
            context.close()
        browser.close()

    report_path = OUT_DIR / f"{PHASE}-home-report.json"
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(report_path)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

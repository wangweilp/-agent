import json
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3150"

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
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--proxy-server=direct://", "--proxy-bypass-list=*"],
        )
        context = browser.new_context(viewport={"width": 375, "height": 812})
        page = context.new_page()
        page.set_default_timeout(60000)
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
        page.goto(BASE_URL + "/login", wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        page.evaluate(
            "(value) => localStorage.setItem('agent-os-auth', value)",
            json.dumps(AUTH_STATE),
        )
        page.goto(BASE_URL + "/home", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            console_messages.append("warning: networkidle timeout; continuing")
        page.get_by_label("打开菜单").click()
        page.wait_for_timeout(350)
        opened = page.evaluate(
            """() => {
                const aside = document.querySelector('aside');
                const rect = aside?.getBoundingClientRect();
                return {
                    left: rect?.left ?? null,
                    right: rect?.right ?? null,
                    bodyOverflow: document.body.style.overflow,
                    overlay: Boolean(document.querySelector('.fixed.inset-0.z-40')),
                };
            }"""
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        closed = page.evaluate(
            """() => {
                const aside = document.querySelector('aside');
                const rect = aside?.getBoundingClientRect();
                return {
                    left: rect?.left ?? null,
                    right: rect?.right ?? null,
                    bodyOverflow: document.body.style.overflow,
                    overlay: Boolean(document.querySelector('.fixed.inset-0.z-40')),
                };
            }"""
        )
        browser.close()
    result = {"opened": opened, "closed": closed, "console": console_messages[-10:]}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    assert opened["left"] is not None and opened["left"] >= -1
    assert opened["bodyOverflow"] == "hidden"
    assert opened["overlay"] is True
    assert closed["left"] is not None and closed["left"] < -200
    assert closed["bodyOverflow"] != "hidden"
    assert closed["overlay"] is False


if __name__ == "__main__":
    main()

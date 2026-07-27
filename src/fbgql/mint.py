"""Interactive session minting — the one piece that needs a real browser.

Run this ONCE, on a machine with a display and (ideally) a residential IP. A human
logs in; we capture the cookie jar to JSON. The scraper then consumes those cookies
headlessly anywhere (VPS, Docker, Apify). This module is NOT imported by the engine
and requires the optional ``[mint]`` extra.
"""

from __future__ import annotations

import json
import time

_REQUIRED = {"c_user", "xs"}


def mint(out_path: str, *, headless: bool = False, timeout: int = 300) -> dict[str, str]:
    """Open a browser, wait for the user to log in, save cookies to ``out_path``."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "mint-session requires the [mint] extra:\n    pip install 'fbgql[mint]'"
        ) from exc

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=opts)
    try:
        driver.get("https://www.facebook.com/login")
        print("A browser window opened. Log in to Facebook (handle any 2FA/checkpoint).")
        print(f"Waiting up to {timeout}s for a logged-in session…")

        deadline = time.time() + timeout
        cookies: dict[str, str] = {}
        while time.time() < deadline:
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            if _REQUIRED.issubset(cookies):
                break
            time.sleep(2)

        if not _REQUIRED.issubset(cookies):
            raise SystemExit("Timed out before a logged-in session appeared (no c_user/xs).")

        # Capture fb_dtsg straight from the logged-in page so runs never depend on
        # headless token derivation. Falls back gracefully if not found.
        fb_dtsg = None
        try:
            from .auth import extract_fb_dtsg
            html = driver.execute_script("return document.documentElement.outerHTML") or ""
            fb_dtsg = extract_fb_dtsg(html)
        except Exception:  # noqa: BLE001 - capture is best-effort
            fb_dtsg = None

        # Wrapped session format: cookies + the captured token. Loaders also accept a
        # plain cookie dict (for cookies pasted into the Apify actor, etc.).
        session = {"cookies": cookies, "c_user": cookies.get("c_user")}
        if fb_dtsg:
            session["fb_dtsg"] = fb_dtsg

        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(session, fh, indent=2)
        token_note = "fb_dtsg captured" if fb_dtsg else "fb_dtsg NOT captured (will derive at run)"
        print(f"Saved {len(cookies)} cookies to {out_path} "
              f"(c_user={cookies.get('c_user')}, {token_note})")
        return cookies
    finally:
        driver.quit()

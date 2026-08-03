"""Capture the CURRENT Facebook GraphQL doc_ids + variable schemas from a real browser.

doc_ids and their variable sets drift when Meta rotates persisted queries — the shipped
constants then fail server-side with ``missing_required_variable_value`` (a stale-query
error), not with bad data. This opens the same browser used for minting, injects your
cookies, browses a page (feed + one post's comments), and records every GraphQL POST it
makes. The output tells you the exact doc_id + variables the live client sends today, so
the shipped payloads/doc_ids can be updated without guessing.

Requires the optional ``[mint]`` extra (Selenium + Chrome). Not imported by the engine.

    fbgql capture --page ronaldo --cookies cookies.json --out captured_queries.json
"""

from __future__ import annotations

import contextlib
import json
import time
import urllib.parse
from typing import Any


def _build_driver(headless: bool):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "capture requires the [mint] extra:\n    pip install 'fbgql[mint]'"
        ) from exc

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # Performance logging streams CDP Network events (with request bodies) into a log
    # we can drain with driver.get_log("performance").
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def _inject_cookies(driver, cookies: dict[str, str]) -> None:
    driver.get("https://www.facebook.com/")
    time.sleep(1.5)
    for name, value in cookies.items():
        # Some cookies (host-only) may be rejected by add_cookie; skip those.
        with contextlib.suppress(Exception):
            driver.add_cookie({"name": name, "value": value, "domain": ".facebook.com"})


def _drain_graphql(driver, seen_ids: set[str], out: list[dict[str, Any]]) -> None:
    """Pull new GraphQL POSTs out of the performance log into ``out`` (deduped by request)."""
    try:
        logs = driver.get_log("performance")
    except Exception:  # noqa: BLE001
        return
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:  # noqa: BLE001
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        params = msg.get("params", {})
        req = params.get("request", {})
        url = req.get("url", "")
        if "/api/graphql" not in url or req.get("method") != "POST":
            continue
        request_id = params.get("requestId")
        if request_id in seen_ids:
            continue
        seen_ids.add(request_id)

        post_data = req.get("postData")
        if not post_data and req.get("hasPostData") and request_id:
            try:
                post_data = driver.execute_cdp_cmd(
                    "Network.getRequestPostData", {"requestId": request_id}
                ).get("postData")
            except Exception:  # noqa: BLE001 - body may have been evicted
                post_data = None
        if not post_data:
            continue

        fields = urllib.parse.parse_qs(post_data)
        friendly = (fields.get("fb_api_req_friendly_name") or [None])[0]
        doc_id = (fields.get("doc_id") or [None])[0]
        raw_vars = (fields.get("variables") or [None])[0]
        if not doc_id:
            continue
        parsed_vars: Any = None
        if raw_vars:
            try:
                parsed_vars = json.loads(raw_vars)
            except Exception:  # noqa: BLE001
                parsed_vars = raw_vars
        out.append({
            "friendly_name": friendly,
            "doc_id": doc_id,
            "variables": parsed_vars,
            "request_id": request_id,
        })


def _scroll(driver, times: int, pause: float, seen_ids: set[str], out: list) -> None:
    for _ in range(times):
        with contextlib.suppress(Exception):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        _drain_graphql(driver, seen_ids, out)


_POST_HREF_MARKERS = ("/posts/", "story_fbid", "/videos/", "pfbid", "/permalink/")


def _page_url(page: str) -> str:
    """Normalize a handle, path, or full Facebook URL into an absolute page URL."""
    page = (page or "").strip()
    if page.startswith("http://") or page.startswith("https://"):
        return page
    return f"https://www.facebook.com/{page.lstrip('/')}"


def _first_post_permalink(driver, captured: list[dict], page: str) -> str | None:
    """Find a post permalink to open (so comment/reply queries fire).

    Two strategies: parse a captured timeline response for a permalink, then fall back
    to scraping post links straight out of the rendered DOM (more robust — the response
    body may have been evicted from the CDP buffer).
    """
    from . import parsing

    # 1) Structured: from a captured timeline response body.
    for rec in captured:
        friendly = (rec.get("friendly_name") or "").lower()
        if "feed" not in friendly and "timeline" not in friendly:
            continue
        rid = rec.get("request_id")
        if not rid:
            continue
        try:
            body = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": rid}
            ).get("body", "")
            posts, _cursor = parsing.parse_posts(body, page)
        except Exception:  # noqa: BLE001
            posts = []
        for p in posts:
            if p.permalink:
                return p.permalink
            if p.post_id:
                return f"https://www.facebook.com/{page}/posts/{p.post_id}"

    # 2) DOM fallback: any anchor pointing at a post permalink.
    try:
        from selenium.webdriver.common.by import By

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
            except Exception:  # noqa: BLE001 - stale element
                continue
            if any(m in href for m in _POST_HREF_MARKERS):
                return href
    except Exception:  # noqa: BLE001
        pass
    return None


# Logical name -> substrings that identify its live friendly_name. Order the matchers
# so "replies" (Depth1…) is distinguished from top-level "comments"
# (CommentsListComponents…) — both contain "commentslist", hence the specific needles.
# ``group_feed`` is separate from ``timeline``: GroupsCometFeed* is not a page/profile
# timeline query and must not be confused with ProfileCometTimelineFeedRefetchQuery.
_QUERY_MATCHERS = {
    "timeline": ("timelinefeed", "profilecomettimeline", "pagefeed", "modernpagefeed"),
    "group_feed": (
        "groupscometfeedregularstoriespaginationquery",
        "groupscometfeedregularstoriespagination",
    ),
    "comments": ("commentslistcomponents", "ufi_comments"),
    "replies": ("depth1comments", "commentreplies", "replieslist"),
}


def _classify(captured: list[dict]) -> dict[str, dict]:
    """Pick the best live query for each logical name (first match wins)."""
    resolved: dict[str, dict] = {}
    for name, needles in _QUERY_MATCHERS.items():
        for rec in captured:
            friendly = (rec.get("friendly_name") or "").lower()
            if any(n in friendly for n in needles):
                resolved[name] = rec
                break
    return resolved


def capture(
    page: str,
    cookies: dict[str, str] | None,
    out_path: str,
    *,
    headless: bool = False,
    feed_scrolls: int = 8,
    comment_scrolls: int = 8,
    timeout: int = 300,
) -> dict[str, Any]:
    """Browse ``page`` in a real browser and record every GraphQL POST it makes."""
    driver = _build_driver(headless)
    seen_ids: set[str] = set()
    captured: list[dict[str, Any]] = []
    try:
        if cookies:
            _inject_cookies(driver, cookies)
        else:
            driver.get("https://www.facebook.com/login")
            print("Log in to Facebook in the browser window…")
            deadline = time.time() + timeout
            while time.time() < deadline:
                names = {c["name"] for c in driver.get_cookies()}
                if {"c_user", "xs"}.issubset(names):
                    break
                time.sleep(2)

        url = _page_url(page)
        print(f"Loading feed for {page!r} ({url}) and scrolling to trigger pagination…")
        driver.get(url)
        time.sleep(5)
        _drain_graphql(driver, seen_ids, captured)
        _scroll(driver, feed_scrolls, 2.5, seen_ids, captured)

        permalink = _first_post_permalink(driver, captured, page)
        if permalink:
            print(f"Opening a post to trigger comment/reply queries: {permalink}")
            driver.get(permalink)
            time.sleep(5)
            _drain_graphql(driver, seen_ids, captured)
            _scroll(driver, comment_scrolls, 2.5, seen_ids, captured)
        else:
            print("Could not auto-locate a post permalink — captured feed queries only.")

        resolved = _classify(captured)
        report = {
            "page": page,
            "resolved": {k: {"doc_id": v["doc_id"],
                             "friendly_name": v["friendly_name"],
                             "variables": v["variables"]}
                         for k, v in resolved.items()},
            "all_queries": [{"friendly_name": r["friendly_name"], "doc_id": r["doc_id"],
                             "variables": r["variables"]}
                            for r in captured],
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        print(f"\nCaptured {len(captured)} GraphQL POST(s) → {out_path}")
        for name in ("timeline", "group_feed", "comments", "replies"):
            rec = resolved.get(name)
            if rec:
                print(f"  {name:10s}: doc_id={rec['doc_id']}  ({rec['friendly_name']})")
            else:
                print(f"  {name:10s}: NOT captured")
        return report
    finally:
        driver.quit()

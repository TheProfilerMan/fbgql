"""Health checks — surface a dead session or a rotated doc_id before a real run.

doc_ids drift when Facebook rotates them; this gives operators a fast signal without
spelunking through a failed scrape.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import auth, config, parsing, payloads, runner
from .errors import SessionInvalid
from .models import Account
from .transport import friendly_headers
from .transport.sync_http import SyncTransport


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_checks(account: Account, page: str | None = None) -> list[Check]:
    checks: list[Check] = []
    transport = SyncTransport()

    # 1. Session / fb_dtsg derivation.
    try:
        session = auth.resolve_session(account, transport)
        detail = ("anonymous (actor 0, no fb_dtsg)" if account.anonymous
                  else f"c_user={session.c_user}, fb_dtsg derived")
        checks.append(Check("session", True, detail))
    except SessionInvalid as exc:
        checks.append(Check("session", False, str(exc)))
        return checks  # nothing else will work without a session

    registry = config.DocIdRegistry()

    # 2. Timeline doc_id — resolve a page and pull one feed page.
    if page:
        try:
            page_id = runner._resolve_page_id(page, session, transport)
            headers = runner._timeline_headers(page_id)
            data = payloads.posts_payload(user_id=page_id, cursor=None, c_user=session.c_user,
                                          fb_dtsg=session.fb_dtsg, doc_id=registry.get("timeline"))
            body = transport.post_form(headers, data, session.cookies, session.proxy)
            parsed = parsing.fb_json(body)
            rejection = parsing.fb_request_error(parsed)
            if rejection:
                checks.append(Check(
                    "doc_id:timeline", False,
                    f"REJECTED (error {rejection['code']}: {rejection['summary']}) — "
                    f"{rejection['description']} "
                    "[account likely restricted/flagged/rate-limited, not a doc_id issue]"))
                return checks
            stale = parsing.graphql_stale_query_error(parsed)
            if stale:
                checks.append(Check(
                    "doc_id:timeline", False,
                    f"STALE QUERY ({stale['message']}) — the timeline doc_id "
                    f"({registry.get('timeline')}) or its variables are out of date; "
                    "Facebook rotated the query. Capture a fresh request from the browser."))
                return checks
            posts, _cursor = parsing.parse_posts(body, page)
            ok = len(posts) > 0
            checks.append(Check("doc_id:timeline", ok,
                                f"page_id={page_id}, posts_found={len(posts)}"
                                + ("" if ok else " (possible doc_id drift)")))

            # 3. Comments doc_id — one page on the first post.
            if posts:
                p = posts[0]
                fid = p.feedback_id or runner.feedback_id_for_post(p.post_id)
                cheaders = friendly_headers(config.FRIENDLY_COMMENTS, referer=p.permalink or config.HOME_URL)
                cdata = payloads.comments_payload(feedback_id=fid, cursor=None,
                                                  c_user=session.c_user, fb_dtsg=session.fb_dtsg,
                                                  doc_id=registry.get("comments"))
                cbody = transport.post_form(cheaders, cdata, session.cookies, session.proxy)
                cpage = parsing.parse_comments_page(parsing.fb_json(cbody))
                cok = bool(cpage.comments) or not cpage.critical_codes
                checks.append(Check("doc_id:comments", cok,
                                    f"comments_on_first_page={len(cpage.comments)}, "
                                    f"critical_codes={cpage.critical_codes}"))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("doc_id:timeline", False, f"{type(exc).__name__}: {exc}"))
    else:
        checks.append(Check("doc_id:timeline", True, "skipped (no --page provided)"))

    return checks

"""Orchestration shared by both engines: resolve sessions, discover posts, bin-pack.

The heavy comment scraping is done by the engines (threaded / async). This module
does the up-front, sequential work once: resolve page id, fetch the post list, resolve
account sessions, and assign posts to workers.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field

from . import auth, config, parsing, payloads, policy
from .errors import RequestRejected, SessionInvalid, TransportError
from .models import Account, Post, ScrapeJob, Session
from .transport.sync_http import SyncTransport

_NUMERIC = re.compile(r"^\d+$")
# Page-id candidate patterns, best-first. The timeline feed query keys on the *feed
# owner / profile* id (e.g. 100064… for a Page), NOT the classic page id (e.g. 1938…
# from delegate_page) — the latter returns an empty ``Page`` node. Facebook serves
# inconsistent HTML (the fb://profile App Link is sometimes absent), so we gather ALL
# candidates and let the caller probe them against the live query. profile/userID
# signals (the feed owner) come first so the working id is usually tried first.
_PAGE_ID_PATTERNS = [
    re.compile(r'fb:\\?/\\?/profile\\?/(\d+)'),        # profile App Link — feed-owner id
    re.compile(r'"userID"\s*:\s*"(\d+)"'),             # feed-owner id in the page's own bootstrap
    re.compile(r'"profile_owner"\s*:\s*"(\d+)"'),
    re.compile(r'fb:\\?/\\?/(?:page|group)\\?/(?:\?id=)?(\d+)'),
    re.compile(r'"delegate_page"\s*:\s*\{\s*"id"\s*:\s*"(\d+)"'),
    re.compile(r'"pageID"\s*:\s*"(\d+)"'),
    re.compile(r'"page_id"\s*:\s*"?(\d+)"?'),
    re.compile(r'"entity_id"\s*:\s*"(\d+)"'),
]
_POST_ID_PATTERNS = [
    re.compile(r'/posts/(\d+)'),
    re.compile(r'story_fbid=(\d+)'),
    re.compile(r'/permalink/(\d+)'),
    re.compile(r'/videos/(\d+)'),
    re.compile(r'(\d{6,})'),
    re.compile(r'(pfbid\w+)'),  # opaque id — base64 feedback trick may not apply
]


def feedback_id_for_post(post_id: str) -> str:
    """Facebook's comment query keys on the base64 of ``feedback:<post_id>``."""
    return base64.b64encode(f"feedback:{post_id}".encode()).decode()


@dataclass
class ExecutionPlan:
    job: ScrapeJob
    posts: list[Post]
    assignment: policy.Assignment
    worker_sessions: list[Session]  # index-aligned with assignment.buckets
    registry: config.DocIdRegistry
    page_name: str | None = None
    resolved_page_id: str | None = None
    meta: dict = field(default_factory=dict)


def _resolve_page_id_candidates(page: str, session: Session,
                                transport: SyncTransport) -> list[str]:
    """All plausible numeric ids for a handle, best-first (feed-owner ids leading).

    Returns a list because a page's HTML exposes several ids (the feed-owner/profile
    id AND the classic Page id) and only one drives the timeline query — the caller
    probes them against the live query to pick the right one.
    """
    if _NUMERIC.match(page):
        return [page]
    from .auth import BROWSER_HEADERS

    handle = page.rstrip("/").split("/")[-1].split("?")[0]
    candidates: list[str] = []
    for url in (f"https://www.facebook.com/{handle}",
                f"https://www.facebook.com/{handle}/about"):
        html = transport.get(url, cookies=session.cookies, proxy=session.proxy,
                             headers=BROWSER_HEADERS)
        for pat in _PAGE_ID_PATTERNS:
            for m in pat.finditer(html):
                v = m.group(1)
                if v and v != "0" and v not in candidates:
                    candidates.append(v)
        if candidates:
            break
    if not candidates:
        raise ValueError(
            f"Could not resolve numeric page id for {page!r}. "
            "Pass the page's numeric id directly (--page 123456), or a full post URL."
        )
    return candidates


def _resolve_page_id(page: str, session: Session, transport: SyncTransport) -> str:
    """Best single id (back-compat for doctor/diagnostics)."""
    return _resolve_page_id_candidates(page, session, transport)[0]


def _post_id_from_url(url: str) -> str:
    for pat in _POST_ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract post id from {url!r}")


def _post_timeline(user_id: str, cursor: str | None, job: ScrapeJob, session: Session,
                   transport: SyncTransport, doc_id: str, page_name: str | None):
    """One timeline POST -> (posts, next_cursor). Raises on rejection/stale-query."""
    data = payloads.posts_payload(
        user_id=user_id, cursor=cursor, c_user=session.c_user,
        fb_dtsg=session.fb_dtsg, doc_id=doc_id,
    )
    body = transport.post_form(_timeline_headers(user_id), data, session.cookies, session.proxy)
    parsed = parsing.fb_json(body)
    parsing.raise_if_rejected(parsed, "timeline")
    parsing.raise_if_doc_id_stale(parsed, "timeline", doc_id)
    return parsing.parse_posts(body, page_name)


def _fetch_posts(user_ids: list[str], job: ScrapeJob, session: Session,
                 transport: SyncTransport, page_name: str | None) -> tuple[list[Post], str | None]:
    """Fetch the page timeline, returning (posts, the id that actually drove the feed).

    The first page also selects the working id: the page HTML yields several candidate
    ids and only the feed-owner id returns timeline units — the rest return an empty
    node — so we try candidates in order until one yields posts.
    """
    doc_id = job_registry(job).get("timeline")
    posts: list[Post] = []

    chosen: str | None = None
    cursor: str | None = None
    for uid in user_ids:
        page_posts, cursor = _post_timeline(uid, None, job, session, transport, doc_id, page_name)
        if page_posts:
            chosen = uid
            _append_unique(posts, page_posts)
            break
    if chosen is None:
        # No candidate returned a feed — surface the id we tried for a clear message.
        return [], (user_ids[0] if user_ids else None)

    empty_pages = 0
    while len(posts) < job.max_posts and cursor:
        time.sleep(1)
        try:
            page_posts, cursor = _post_timeline(chosen, cursor, job, session, transport,
                                                doc_id, page_name)
        except (SessionInvalid, RequestRejected, TransportError):
            # Blocked / logged-out mid-pagination on a hostile IP — keep the posts we
            # already collected (page 1+) and let the run proceed rather than losing all.
            break
        if not page_posts:
            empty_pages += 1
            if empty_pages >= 3 or not cursor:
                break
            time.sleep(2)
            continue
        empty_pages = 0
        _append_unique(posts, page_posts)
    return posts[: job.max_posts], chosen


def _append_unique(posts: list[Post], new: list[Post]) -> None:
    seen = {p.post_id for p in posts}
    for p in new:
        if p.post_id not in seen:
            posts.append(p)
            seen.add(p.post_id)


def _timeline_headers(user_id: str) -> dict[str, str]:
    # Match the proven reference: bare BASE_HEADERS + origin + referer, and NO
    # x-fb-friendly-name on the timeline request (comments/replies do send it, the
    # timeline feed refetch does not). Avoids any friendly-name/doc_id cross-check.
    headers = dict(config.BASE_HEADERS)
    headers["origin"] = "https://www.facebook.com"
    headers["referer"] = f"https://www.facebook.com/profile.php?id={user_id}"
    return headers


def job_registry(job: ScrapeJob) -> config.DocIdRegistry:
    return config.DocIdRegistry()


def _resolve_sessions(job: ScrapeJob, transport: SyncTransport) -> tuple[Session, Session | None]:
    # Anonymous is the default: no account supplied means logged-out public scraping.
    # Supplying an account whose cookies lack c_user is still a hard failure — that's a
    # dead session, not an anonymous one, and it must not silently degrade.
    if job.anonymous or not job.accounts:
        # One actor-0 session; no dual-account routing (there are no accounts to route).
        proxy = job.accounts[0].proxy if job.accounts else None
        return auth.anonymous_session(Account.anonymous_account(proxy=proxy)), None
    primary = auth.resolve_session(job.accounts[0], transport)
    mega: Session | None = None
    mega_account = next((a for a in job.accounts[1:] if a.role == "mega"), None)
    if mega_account is None and len(job.accounts) > 1:
        mega_account = job.accounts[1]
    if mega_account is not None:
        candidate = auth.resolve_session(mega_account, transport)
        # Dual-account only helps with two *distinct* c_users.
        if candidate.c_user and candidate.c_user != primary.c_user:
            mega = candidate
    return primary, mega


def prepare(job: ScrapeJob) -> ExecutionPlan:
    """Do the sequential up-front work and return an execution plan for an engine."""
    transport = SyncTransport()
    registry = config.DocIdRegistry()
    primary, mega = _resolve_sessions(job, transport)

    workers, _cap = job.resolved_policy()
    page_name = job.page

    if job.post_url:
        post_id = _post_id_from_url(job.post_url)
        posts = [Post(post_id=post_id, feedback_id=feedback_id_for_post(post_id),
                      text="", permalink=job.post_url, comment_count=0, page_name=page_name)]
        resolved_id = None
    else:
        if not job.page:
            raise ValueError("ScrapeJob needs either page or post_url")
        candidates = _resolve_page_id_candidates(job.page, primary, transport)
        posts, resolved_id = _fetch_posts(candidates, job, primary, transport, page_name)
        for p in posts:
            if not p.feedback_id:
                p.feedback_id = feedback_id_for_post(p.post_id)

    assignment = policy.assign_posts(posts, workers, job.mega_threshold)

    # Route sessions: mega worker gets the mega session when available.
    worker_sessions: list[Session] = []
    for w in range(len(assignment.buckets)):
        if assignment.mega_worker == w and mega is not None:
            worker_sessions.append(mega)
        else:
            worker_sessions.append(primary)

    return ExecutionPlan(
        job=job,
        posts=posts,
        assignment=assignment,
        worker_sessions=worker_sessions,
        registry=registry,
        page_name=page_name,
        resolved_page_id=resolved_id,
        meta={"mega_used": mega is not None, "mega_post_id": assignment.mega_post_id,
              "access_mode": "anonymous" if job.anonymous else "authenticated"},
    )


def summarize(job: ScrapeJob, post_results: list) -> dict:
    """Roll up per-post results into run-level coverage numbers."""
    from statistics import median

    total_scraped = sum(p.total_scraped for p in post_results)
    total_fb = sum(p.post.comment_count for p in post_results)
    covs = [p.coverage for p in post_results if p.post.comment_count]
    return {
        "weighted_coverage": (total_scraped / total_fb) if total_fb else 0.0,
        "median_coverage": median(covs) if covs else 0.0,
        "total_scraped": total_scraped,
        "total_fb_comments": total_fb,
    }

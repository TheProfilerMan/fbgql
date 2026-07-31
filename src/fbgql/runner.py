"""Orchestration shared by both engines: resolve sessions, discover posts, bin-pack.

The heavy comment scraping is done by the engines (threaded / async). This module
does the up-front, sequential work once: resolve page/group id, fetch the post list,
resolve account sessions, and assign posts to workers.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field

from . import auth, config, parsing, payloads, policy
from .errors import RequestRejected, SessionInvalid, TransportError
from .models import Account, Post, ScrapeJob, Session
from .progress import emit
from .transport.sync_http import SyncTransport

_NUMERIC = re.compile(r"^\d+$")
_GROUP_URL = re.compile(
    r"(?:https?://)?(?:www\.)?facebook\.com/groups/([^/?#]+)", re.IGNORECASE
)
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
    re.compile(r'"groupID"\s*:\s*"(\d+)"'),            # public group bootstrap
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


def _classify_target(page: str) -> tuple[str, str]:
    """Return ``(kind, handle_or_id)`` where kind is ``group`` or ``page``.

    ``page`` covers Facebook Pages and user profiles (same timeline query).
    """
    page = (page or "").strip()
    m = _GROUP_URL.search(page)
    if m:
        return "group", m.group(1)
    # Bare path fragments like "groups/123" from some callers.
    parts = [p for p in page.replace("https://", "").replace("http://", "").split("/") if p]
    if "groups" in parts:
        idx = parts.index("groups")
        if idx + 1 < len(parts):
            return "group", parts[idx + 1].split("?")[0]
    handle = page.rstrip("/").split("/")[-1].split("?")[0]
    return "page", handle


def _candidate_html_urls(page: str, kind: str, handle: str) -> list[str]:
    """URLs to fetch when resolving a numeric id from HTML."""
    if kind == "group":
        return [
            f"https://www.facebook.com/groups/{handle}",
            f"https://www.facebook.com/{handle}",
        ]
    urls = [f"https://www.facebook.com/{handle}", f"https://www.facebook.com/{handle}/about"]
    # If the caller passed a full non-group URL, try it first (vanity / profile.php).
    if page.startswith("http") and page.rstrip("/") not in urls:
        urls.insert(0, page.split("?")[0])
    return urls


def _resolve_page_id_candidates(page: str, session: Session,
                                transport: SyncTransport) -> list[str]:
    """All plausible numeric ids for a handle, best-first (feed-owner ids leading).

    Returns a list because a page's HTML exposes several ids (the feed-owner/profile
    id AND the classic Page id) and only one drives the timeline query — the caller
    probes them against the live query to pick the right one.
    """
    kind, handle = _classify_target(page)
    if _NUMERIC.match(handle):
        return [handle]
    from .auth import BROWSER_HEADERS

    candidates: list[str] = []
    for url in _candidate_html_urls(page, kind, handle):
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
            f"Could not resolve numeric id for {page!r}. "
            "The target may be private or login-gated from this IP — try a residential "
            "proxy in a matching country, pass the numeric id, or a full post URL."
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


def _usable_posts(posts: list[Post]) -> list[Post]:
    """Drop empty story shells that group feeds interleave with real posts."""
    out: list[Post] = []
    for p in posts:
        if not p.post_id:
            continue
        if p.text or p.permalink or p.feedback_id or p.comment_count:
            out.append(p)
    return out


def _post_timeline(user_id: str, cursor: str | None, job: ScrapeJob, session: Session,
                   transport: SyncTransport, doc_id: str, page_name: str | None):
    """One timeline POST -> (posts, next_cursor). Raises on rejection/stale-query."""
    data = payloads.posts_payload(
        user_id=user_id, cursor=cursor, c_user=session.c_user,
        fb_dtsg=session.fb_dtsg, doc_id=doc_id,
        after_time=job.after_time, before_time=job.before_time,
    )
    body = transport.post_form(_timeline_headers(user_id), data, session.cookies, session.proxy)
    parsed = parsing.fb_json(body)
    parsing.raise_if_rejected(parsed, "timeline")
    parsing.raise_if_doc_id_stale(parsed, "timeline", doc_id)
    posts, next_cursor = parsing.parse_posts(body, page_name)
    return _usable_posts(posts), next_cursor


def _post_group_feed(group_id: str, cursor: str | None, job: ScrapeJob, session: Session,
                     transport: SyncTransport, doc_id: str, page_name: str | None):
    """One group-feed POST -> (posts, next_cursor)."""
    data = payloads.group_feed_payload(
        group_id=group_id, cursor=cursor, c_user=session.c_user,
        fb_dtsg=session.fb_dtsg, doc_id=doc_id,
    )
    body = transport.post_form(
        _group_feed_headers(group_id), data, session.cookies, session.proxy
    )
    parsed = parsing.fb_json(body)
    parsing.raise_if_rejected(parsed, "group_feed")
    parsing.raise_if_doc_id_stale(parsed, "group_feed", doc_id)
    posts, next_cursor = parsing.parse_posts(body, page_name)
    # Prefer the group_feed connection cursor when present.
    node = (parsed.get("data") or {}).get("node") or {}
    page_info = (node.get("group_feed") or {}).get("page_info") or {}
    if page_info.get("end_cursor"):
        next_cursor = page_info["end_cursor"]
    elif page_info.get("has_next_page") is False:
        next_cursor = None
    return _usable_posts(posts), next_cursor


def _uses_date_window(job: ScrapeJob) -> bool:
    return job.after_time is not None or job.before_time is not None


def _post_in_date_range(post: Post, job: ScrapeJob) -> bool:
    """True if ``post`` falls inside the job's optional [after_time, before_time) window."""
    if not _uses_date_window(job):
        return True
    ts = post.created_time
    if ts is None:
        return False
    if job.after_time is not None and ts < job.after_time:
        return False
    if job.before_time is not None and ts >= job.before_time:
        return False
    return True


def _past_date_window(page_posts: list[Post], job: ScrapeJob) -> bool:
    """True when the feed (newest-first) has scrolled past ``after_time``."""
    if job.after_time is None:
        return False
    for p in page_posts:
        if p.created_time is not None and p.created_time < job.after_time:
            return True
    return False


def _under_post_cap(posts: list[Post], job: ScrapeJob) -> bool:
    """Whether we should keep paginating under the max_posts cap.

    Date-filtered runs ignore ``max_posts`` and stop on the date window (or end of feed)
    instead — otherwise a default of 20 would truncate a month of posts.
    """
    if _uses_date_window(job):
        return True
    return len(posts) < job.max_posts


def _paginate_feed(
    fetch_page,
    ids: list[str],
    job: ScrapeJob,
) -> tuple[list[Post], str | None]:
    """Probe ids until one yields posts, then paginate that id.

    Without a date window: stop at ``max_posts``.
    With ``after_time`` / ``before_time``: keep every in-range post and stop once the
    (newest-first) feed scrolls older than ``after_time`` (or the cursor ends).
    ``max_posts`` is ignored while a date window is set.
    """
    posts: list[Post] = []
    chosen: str | None = None
    cursor: str | None = None
    feed_page = 0
    for uid in ids:
        emit(job, f"Probing feed id {uid}…")
        page_posts, cursor = fetch_page(uid, None)
        feed_page += 1
        if page_posts:
            chosen = uid
            kept = [p for p in page_posts if _post_in_date_range(p, job)]
            _append_unique(posts, kept)
            emit(
                job,
                f"Feed page {feed_page}: got {len(page_posts)} posts, "
                f"kept {len(kept)} (total {len(posts)})"
                + (f", cursor={'yes' if cursor else 'end'}")
            )
            if _past_date_window(page_posts, job):
                emit(job, "Reached end of date window on first feed page")
                cursor = None
            break
        emit(job, f"Feed id {uid}: no posts")
    if chosen is None:
        return [], (ids[0] if ids else None)

    empty_pages = 0
    while _under_post_cap(posts, job) and cursor:
        time.sleep(1)
        try:
            emit(job, f"Fetching feed page {feed_page + 1}…")
            page_posts, cursor = fetch_page(chosen, cursor)
            feed_page += 1
        except (SessionInvalid, RequestRejected, TransportError) as exc:
            # Blocked mid-pagination — keep what we have.
            emit(job, f"Feed pagination stopped ({type(exc).__name__}); keeping {len(posts)} posts")
            break
        if not page_posts:
            empty_pages += 1
            emit(job, f"Feed page {feed_page}: empty ({empty_pages}/3)")
            if empty_pages >= 3 or not cursor:
                break
            time.sleep(2)
            continue
        empty_pages = 0
        kept = [p for p in page_posts if _post_in_date_range(p, job)]
        _append_unique(posts, kept)
        emit(
            job,
            f"Feed page {feed_page}: got {len(page_posts)} posts, "
            f"kept {len(kept)} (total {len(posts)})"
        )
        if _past_date_window(page_posts, job):
            emit(job, "Reached end of date window — stopping feed pagination")
            break
    if _uses_date_window(job):
        return posts, chosen
    return posts[: job.max_posts], chosen


def _fetch_timeline_posts(user_ids: list[str], job: ScrapeJob, session: Session,
                          transport: SyncTransport,
                          page_name: str | None) -> tuple[list[Post], str | None]:
    doc_id = job_registry(job).get("timeline")

    def _page(uid: str, cursor: str | None):
        return _post_timeline(uid, cursor, job, session, transport, doc_id, page_name)

    return _paginate_feed(_page, user_ids, job)


def _fetch_group_posts(group_ids: list[str], job: ScrapeJob, session: Session,
                       transport: SyncTransport,
                       page_name: str | None) -> tuple[list[Post], str | None]:
    doc_id = job_registry(job).get("group_feed")

    def _page(uid: str, cursor: str | None):
        return _post_group_feed(uid, cursor, job, session, transport, doc_id, page_name)

    return _paginate_feed(_page, group_ids, job)


def _fetch_posts(user_ids: list[str], job: ScrapeJob, session: Session,
                 transport: SyncTransport, page_name: str | None,
                 *, prefer_group: bool = False) -> tuple[list[Post], str | None, str]:
    """Fetch posts from a page/profile timeline and/or a group feed.

    Returns ``(posts, resolved_id, feed_kind)`` where ``feed_kind`` is
    ``timeline`` or ``group_feed``.
    """
    if prefer_group:
        posts, chosen = _fetch_group_posts(user_ids, job, session, transport, page_name)
        if posts:
            return posts, chosen, "group_feed"
        # Fall back in case the URL looked like a group but the id is a page/profile.
        posts, chosen = _fetch_timeline_posts(user_ids, job, session, transport, page_name)
        return posts, chosen, "timeline"

    posts, chosen = _fetch_timeline_posts(user_ids, job, session, transport, page_name)
    if posts:
        return posts, chosen, "timeline"
    # Timeline returned an empty Group/User node — try the group feed query.
    posts, chosen = _fetch_group_posts(user_ids, job, session, transport, page_name)
    return posts, chosen, "group_feed"


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


def _group_feed_headers(group_id: str) -> dict[str, str]:
    headers = dict(config.BASE_HEADERS)
    headers["origin"] = "https://www.facebook.com"
    headers["referer"] = f"https://www.facebook.com/groups/{group_id}"
    headers["x-fb-friendly-name"] = config.FRIENDLY_GROUP_FEED
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
    emit(job, "Resolving session…")
    primary, mega = _resolve_sessions(job, transport)
    emit(job, f"Session ready (access={'anonymous' if job.anonymous or not job.accounts else 'authenticated'})")

    workers, _cap = job.resolved_policy()
    page_name = job.page
    feed_kind = "post_url"

    if job.post_url:
        emit(job, f"Single-post mode: {job.post_url}")
        post_id = _post_id_from_url(job.post_url)
        posts = [Post(post_id=post_id, feedback_id=feedback_id_for_post(post_id),
                      text="", permalink=job.post_url, comment_count=0, page_name=page_name)]
        resolved_id = None
    else:
        if not job.page:
            raise ValueError("ScrapeJob needs either page or post_url")
        kind, _handle = _classify_target(job.page)
        emit(job, f"Resolving numeric id for {job.page!r} ({kind})…")
        candidates = _resolve_page_id_candidates(job.page, primary, transport)
        emit(job, f"Id candidates: {candidates}")
        emit(job, "Discovering posts from feed…")
        posts, resolved_id, feed_kind = _fetch_posts(
            candidates, job, primary, transport, page_name,
            prefer_group=(kind == "group"),
        )
        for p in posts:
            if not p.feedback_id:
                p.feedback_id = feedback_id_for_post(p.post_id)

    emit(
        job,
        f"Discovered {len(posts)} post(s) via {feed_kind}"
        + (f" (id={resolved_id})" if resolved_id else "")
        + ("; posts-only — skipping comments" if job.posts_only else "; scraping comments…"),
    )

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
              "access_mode": "anonymous" if job.anonymous else "authenticated",
              "feed_kind": feed_kind, "target_kind": (
                  "post" if job.post_url else _classify_target(job.page or "")[0]
              )},
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

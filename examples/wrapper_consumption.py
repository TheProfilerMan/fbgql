"""How a SEPARATE backend-wrapper repo consumes this package.

The wrapper is its own repo. It installs fbgql from git (or a private index) — the
monorepo layout (core + apify/ actor) does not affect it; pip installs only src/fbgql.

    # wrapper's pyproject.toml
    dependencies = ["fbgql @ git+https://github.com/bsho5/fbgql.git@v0.1.0"]

The wrapper owns: loading accounts/secrets, choosing pages/schedule, and POSTing
results to a backend. It does NOT own worker/reply-cap logic — that lives in fbgql.
"""

from __future__ import annotations

import os

import requests  # the wrapper's own dependency

from fbgql import Account, Profile, ScrapeJob, Scraper, SessionInvalid


def scrape_and_upload(page: str, cookies: dict, backend_url: str, api_key: str) -> None:
    job = ScrapeJob(
        page=page,
        max_posts=20,
        profile=Profile.DEFAULT,
        engine="threads",
        accounts=[Account(cookies=cookies, proxy=os.getenv("PROXY"))],
    )

    try:
        # Stream so the backend receives posts incrementally on long runs.
        for post in Scraper().stream(job):
            requests.post(
                f"{backend_url}/api/event",
                json={"platform": "facebook", "page": page, "post": post.to_dict()},
                headers={"x-api-key": api_key},
                timeout=30,
            )
    except SessionInvalid:
        # Alert a human to re-mint cookies — an ephemeral worker cannot recover.
        requests.post(
            f"{backend_url}/api/alert",
            json={"kind": "session_invalid", "platform": "facebook", "page": page},
            headers={"x-api-key": api_key},
            timeout=30,
        )
        raise


if __name__ == "__main__":
    import json

    with open("cookies.json", encoding="utf-8") as fh:
        scrape_and_upload(
            page="facebook",
            cookies=json.load(fh),
            backend_url=os.getenv("DAGEEGA_BACKEND_URL", "http://localhost:3000"),
            api_key=os.getenv("DAGEEGA_API_KEY", ""),
        )

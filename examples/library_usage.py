"""Minimal library usage — run a job and print coverage.

    python examples/library_usage.py ZainSudan cookies.json
"""

from __future__ import annotations

import json
import sys

from fbgql import Account, Profile, ScrapeJob, Scraper


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "ZainSudan"
    cookies_path = sys.argv[2] if len(sys.argv) > 2 else "cookies.json"

    with open(cookies_path, encoding="utf-8") as fh:
        cookies = json.load(fh)

    job = ScrapeJob(
        page=page,
        max_posts=20,
        profile=Profile.DEFAULT,   # 3 workers, reply cap 1500
        engine="threads",          # or "async"
        accounts=[Account(cookies=cookies)],
    )

    # One-shot:
    result = Scraper().run(job)
    print(f"weighted coverage: {result.weighted_coverage:.1%} over {len(result.posts)} posts")
    result.to_json("out/result.json")

    # Or stream per-post as they complete:
    # for post in Scraper().stream(job):
    #     print(post.post.post_id, post.coverage)


if __name__ == "__main__":
    main()

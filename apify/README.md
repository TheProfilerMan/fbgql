Scrape comments and replies from public Facebook posts. Point the Actor at a Facebook
page to pull comments across its recent posts, or at a single post URL to scrape just
that thread. For every comment you get the author, text, reaction count, timestamp, and
any attached media, plus one level of replies, returned as structured JSON.

**No Facebook account, login, or cookies required.** The Actor reads public content the
way a logged-out visitor does, so there is nothing to set up and no credentials to hand
over. Just enter a page or post URL and run it.

## What the Facebook Comments Scraper does

- Scrapes **comments and replies** from public Facebook page posts, or from one post URL.
- Needs **no login** — no cookies, no account, no session to keep alive.
- Works **per page** (recent posts) or **per post** (a single permalink).
- Paginates comments **to exhaustion**, not just the first page.
- Returns a **structured JSON** item per post, exportable to CSV, Excel, or JSON.
- Streams results to the dataset as each post finishes, so you see output while it runs.
- Runs through **residential proxies** to reduce blocks.

## What data it extracts

For each post: the post id, text, permalink, and Facebook's reported comment count, plus
the scraped comments. For each comment and reply:

- `author` — display name
- `text` — comment body (empty for media-only comments)
- `reaction_count`
- `created_time` — unix timestamp
- `media` — attached photo/sticker, or `null`
- `replies` — one level of nested replies, same shape

## How to scrape Facebook comments

### 1. Set the input

Set `pageOrUrl` to a page handle, page URL, numeric page id, or a single post URL.
Everything else has sensible defaults.

```json
{ "pageOrUrl": "facebook", "maxPosts": 3 }
```

### 2. Run

Start the run. Results appear in the dataset, one item per post, as each post completes.

That's it — there is no credential step.

## Input

| Field | Required | Notes |
|-------|----------|-------|
| `pageOrUrl` | yes | Page handle/URL/numeric id, or a single post URL (comments only). |
| `proxyConfiguration` | no | Apify residential proxy, sticky per run (on by default). |
| `profile` | no | `default` (recommended), `tops_only` (no replies), `full_replies`. |
| `engine` | no | `async` (default, streaming) or `threads`. |
| `maxPosts` | no | Max recent posts to scrape when given a page (default 20). |
| `workers`, `replyFbCap`, `minIntervalSec`, `megaThreshold` | no | Advanced tuning. |

## Output

One dataset item per post:

```json
{
  "schema_version": 1,
  "post": {"post_id": "...", "text": "...", "permalink": "...", "comment_count": 74},
  "tops": 42, "replies": 29, "total_scraped": 71, "coverage": 0.96,
  "comments": [
    {"comment_id": "...", "author": "...", "text": "...", "reaction_count": 4,
     "created_time": 1690000000, "media": null,
     "replies": [{"comment_id": "...", "author": "...", "text": "..."}]}
  ]
}
```

## What it can and cannot reach

Because the Actor is logged out, it sees exactly what any anonymous visitor sees:

- ✅ Public page posts, their comments, and one level of replies
- ❌ Private groups and profiles
- ❌ Login-gated, age-gated, or geo-restricted posts

If a target needs a login to view in your own browser, this Actor cannot reach it either.

## Comment coverage and rate limits

How completely a thread is scraped is bounded by Facebook's rate limits, not by the
Actor. Facebook's `comment_count` also includes comments the API will not return
(deleted, hidden, or nested deeper than one level), so `coverage` below 1.0 is normal —
typical measured coverage is around 90–95%. The `default` profile balances coverage
against run time. If you hit blocks, raise `minIntervalSec`, lower `workers`, or use
`tops_only`.

## Pricing

The Actor itself is free. You only pay for the Apify platform resources a run consumes
(compute units, and residential proxy traffic if enabled).

## Avoiding blocks

- Keep the residential proxy on. Since there is no account involved, the only thing
  Facebook can throttle is the IP — a good proxy is the single biggest reliability factor.
- Prefer fewer `workers` and a higher `minIntervalSec` over raw speed.
- A blocked run costs only a retry; there is no account to be checkpointed or banned.

## FAQ

**Do I need a Facebook account?** No. The Actor scrapes public content logged out and
never asks for credentials.

**Why don't you accept cookies for more coverage?** Handing a Facebook session to a
third-party actor is a credential risk we don't think users should take, and measured
coverage on public pages is 90–95% without one. Developers who need login-gated content
can use the underlying `fbgql` library or CLI directly with their own session.

**Can I scrape a single post instead of a whole page?** Yes — pass the post URL as
`pageOrUrl`.

**Why did I get fewer comments than Facebook shows?** Facebook's count includes
deleted/hidden/deeply-nested comments the API will not return. See coverage above.

**Why did a run fail with a login wall?** The target isn't publicly visible, or the IP is
blocked. Enable/rotate the residential proxy and retry.

## Legal and data protection

Facebook comments contain personal data (author names). Operating this Actor carries
data-protection obligations, and automated scraping may breach Facebook's Terms of
Service. You are responsible for having a lawful basis for the data you collect and for
honoring data-subject requests. See
[LEGAL.md](https://github.com/bsho5/fbgql/blob/master/LEGAL.md).

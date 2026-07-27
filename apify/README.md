# Facebook Post & Comment Scraper (GraphQL)

Scrape a Facebook **page's posts** and their **comments + replies** (one level) via
the GraphQL API. Thin adapter over the [`fbgql`](../README.md) engine.

> ⚠️ **Bring your own account.** This actor does not log in for you. You provide your
> own Facebook **cookies** as a secret input. Scraping may violate Facebook's Terms of
> Service and involves **personal data** (comment author names) — see
> [Legal & data protection](#legal--data-protection).

## Input

| Field | Required | Notes |
|-------|----------|-------|
| `pageOrUrl` | ✅ | Page handle/URL/numeric id, or a single post URL (comments only). |
| `cookies` | ✅ | Your logged-in cookie jar as JSON (**secret**). See below. |
| `proxyConfiguration` | — | Apify **residential** proxy, sticky per run (default on). |
| `profile` | — | `default` (recommended), `tops_only`, `full_replies`. |
| `engine` | — | `async` (default, streaming) or `threads`. |
| `maxPosts`, `workers`, `replyFbCap`, `minIntervalSec`, `megaThreshold` | — | Tuning. |

### Getting your cookies

Run once locally (needs the `[mint]` extra), then paste the resulting JSON into the
`cookies` secret:

```bash
pip install "fbgql[mint]"
fbgql mint-session --out cookies.json
```

`cookies` looks like `{"c_user": "...", "xs": "...", "datr": "..."}`. Mint from an IP
in the same region you plan to run the proxy from, to reduce checkpoints.

## Output

One dataset item per post (schema v1):

```json
{
  "schema_version": 1,
  "post": {"post_id": "...", "text": "...", "permalink": "...", "comment_count": 1234},
  "tops": 210, "replies": 87, "total_scraped": 297, "coverage": 0.83,
  "comments": [
    {"comment_id": "...", "author": "...", "text": "...", "reaction_count": 4,
     "created_time": 1690000000, "media": null,
     "replies": [{"comment_id": "...", "author": "...", "text": "..."}]}
  ]
}
```

## Coverage & rate limits

Comment coverage on large threads is bounded by Facebook's rate limits. The `default`
profile balances coverage against wall time (reference: ~77% weighted coverage on a
hard page). Concurrent reply requests throttle hardest — raise `minIntervalSec` or use
`tops_only` if you hit blocks. A dead session fails the run with a clear "re-mint
cookies" message.

## Monetization

Pay-per-event: charged per scraped post (`post-scraped`). Configure event pricing in
the actor's monetization settings.

## Build (maintainers)

This actor lives in a monorepo. Build with the **repository root** as the Docker build
context and the Dockerfile at `apify/Dockerfile` (Apify's git integration does this by
default when you set the Dockerfile path).

## Legal & data protection

Facebook comments contain **personal data**. Publishing/operating this actor carries
GDPR-style obligations, and automated scraping may breach Facebook's ToS. You are
responsible for a lawful basis and for honoring data-subject requests. See
[`LEGAL.md`](../LEGAL.md).

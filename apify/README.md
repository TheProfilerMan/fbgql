# Facebook Comment Scraper — free, no login, no cookies

**This is a free Apify Facebook comments scraper.** Extract public Facebook post
comments, replies, authors, reaction counts, and timestamps as structured JSON —
**$0 developer fee from us**. You only pay Apify's small platform usage (compute +
residential proxy traffic). No Facebook account, login, or cookies required.

> Looking for a **free Facebook scraper** on Apify? This Actor scrapes public page
> posts and comment threads logged out — the same content any anonymous visitor sees.
> Click **Run**, enter a page or post URL, export to CSV/Excel/JSON.

## What can this free Facebook comment scraper do?

- **Scrape Facebook comments and replies** from public page posts or a single post URL
- **No login** — no cookies, no account, no session to maintain
- **Paginate comments to exhaustion**, not just the first page
- **Stream results** to the dataset as each post finishes
- **Export** to CSV, Excel, JSON, or pull via Apify API
- **Schedule** runs, monitor failures, and integrate with Zapier/Make/n8n
- **High comment coverage** on public threads (see [coverage](#comment-coverage-and-rate-limits))

## Sample output

One dataset item per post:

```json
{
  "schema_version": 1,
  "post": {
    "post_id": "1234567890",
    "text": "Check out our new product launch!",
    "permalink": "https://www.facebook.com/...",
    "comment_count": 74
  },
  "tops": 42,
  "replies": 29,
  "total_scraped": 71,
  "coverage": 0.96,
  "comments": [
    {
      "comment_id": "...",
      "author": "Jane Doe",
      "text": "Love this!",
      "reaction_count": 4,
      "created_time": 1690000000,
      "media": null,
      "replies": [
        {"comment_id": "...", "author": "Brand Page", "text": "Thank you!"}
      ]
    }
  ]
}
```

## What data can you extract from Facebook?

| Field | Description |
|-------|-------------|
| `post_id`, `text`, `permalink` | Post identity and content |
| `comment_count` | Facebook's reported total |
| `author` | Commenter's display name |
| `text` | Comment body |
| `reaction_count` | Reactions on the comment |
| `created_time` | Unix timestamp |
| `media` | Attached photo/sticker, or `null` |
| `replies` | One level of nested replies |
| `coverage` | Fraction of `comment_count` actually returned |

## Use cases

- **Brand monitoring** — track what people say on your Facebook page
- **Sentiment analysis** — export comment text for NLP pipelines
- **Competitive research** — scrape public competitor page threads
- **Market research** — collect audience reactions on viral posts
- **LLM training data** — public comment threads as structured text

## How to use this free Facebook scraper on Apify

### Quick start

1. Click **Try for free** / **Run**
2. Set **Page or post URL** — e.g. `facebook` or a full post link
3. Leave the defaults (residential proxy on, `maxPosts: 1`)
4. Start the run — results stream into the **Dataset** tab as each post finishes

Default input:

```json
{ "pageOrUrl": "facebook", "maxPosts": 1 }
```

That's it. No credential step.

**How long a run takes depends entirely on the target.** Comments are paginated to
exhaustion — there is no page cap — so a post with tens of comments finishes quickly and
a post with thousands takes much longer and uses proportionally more proxy traffic. Run
`maxPosts: 1` first, look at the run's duration and proxy usage on your own target page,
then scale up from a number you have actually measured.

### Task examples

Copy any of these into a new **Task** on this Actor's page (Tasks → Create task):

| Task | Input | Best for |
|------|-------|----------|
| Smallest run | `{"pageOrUrl": "facebook", "maxPosts": 1}` | Verify the scraper works |
| Monitor a page | `{"pageOrUrl": "yourbrand", "maxPosts": 5}` | Daily brand monitoring |
| Single viral post | `{"pageOrUrl": "https://www.facebook.com/.../posts/..."}` | Deep-dive one thread |
| Sentiment batch | `{"pageOrUrl": "competitor", "maxPosts": 10, "profile": "default"}` | Research export |

Pre-made configs live in [`.actor/task-examples/`](.actor/task-examples/) (when developing
from `apify/`) and [`.actor/task-examples/`](../.actor/task-examples/) (repo-root actor
definition) — same files, kept in sync.

## Is this Facebook comments scraper free?

**Yes — the Actor itself is 100% free.** We charge **$0** per run, per post, and per
comment. There is no rental fee and no pay-per-result markup from the developer.

You only pay **Apify platform usage** — the infrastructure cost of running on Apify:

| Cost component | What it is | Driven by |
|----------------|------------|-----------|
| **Compute units (CUs)** | CPU + RAM while the Actor runs | How long the run takes, i.e. how many comments it paginates |
| **Residential proxy** | Traffic through Apify residential IPs (on by default) | GB transferred — usually the dominant cost here |
| **Dataset storage** | Storing exported results | Negligible for most jobs |

We deliberately don't quote a per-post price, because it isn't ours to quote: it depends
on Apify's current rates, your plan, and above all how many comments the posts you target
actually have. Run `maxPosts: 1` on **your** page, read the compute and proxy usage Apify
reports for that run, and scale from that figure. Current rates are on
[Apify pricing](https://apify.com/pricing); Apify's free plan includes monthly credits
that cover small runs.

### Want zero Apify fees? Run it locally for free

This scraper is **open source (MIT)**. Clone the repo and run on your own machine —
no Apify account needed, no platform charges:

```bash
git clone https://github.com/bsho5/fbgql.git
cd fbgql
./run.sh doctor              # smoke test — checks the API still answers (no login)
./run.sh facebook 1          # scrape 1 post, anonymous, free
```

Or install as a library/CLI:

```bash
pip install -e .
fbgql scrape --page facebook --posts 3 --out out/result.json
```

You bring your own IP (or your own proxy). The Apify Actor is a thin hosted wrapper
around the same [`fbgql`](https://github.com/bsho5/fbgql) engine — same output, your
infrastructure.

## Input

| Field | Required | Notes |
|-------|----------|-------|
| `pageOrUrl` | yes | Page handle/URL/numeric id, or a single post URL |
| `maxPosts` | no | Max recent posts when scraping a page (default 1; ignored for post URLs) |
| `proxyConfiguration` | no | Apify residential proxy, sticky per run (on by default) |
| `profile` | no | `default` (recommended), `tops_only`, `full_replies` |
| `engine` | no | `async` (default, streaming) or `threads` |
| `workers`, `replyFbCap`, `minIntervalSec`, `megaThreshold` | no | Advanced tuning |

## What it can and cannot reach

Because the Actor is logged out, it sees exactly what any anonymous visitor sees:

- ✅ Public page posts, comments, and one level of replies
- ❌ Private groups and profiles
- ❌ Login-gated, age-gated, or geo-restricted posts

## Comment coverage and rate limits

Coverage is bounded by Facebook's rate limits, not by an artificial cap in the Actor.
Facebook's `comment_count` also includes deleted, hidden, or deeply nested comments the
API will not return, so `coverage` below 1.0 is normal. Our own logged-out test runs on
public pages measured **87–94%** (`coverage` is reported per post in every dataset item,
so you can check it against your own targets rather than take ours). If you hit blocks,
raise `minIntervalSec`, lower `workers`, or use `tops_only`.

## Avoiding blocks

- Keep the residential proxy on — the IP is the main reliability lever
- Prefer fewer `workers` and a higher `minIntervalSec` over raw speed
- A blocked run costs only a retry; there is no account to checkpoint

## FAQ

**Is this a free Facebook comments scraper on Apify?**
Yes. Zero developer fee. You only pay Apify platform usage (compute + proxy).

**Is this a free Facebook scraper (posts + comments)?**
Yes for public content — each dataset item includes the post and its comment thread.

**Do I need a Facebook account?**
No. The Actor scrapes public content logged out and never asks for credentials.

**Why don't you accept cookies?**
A public Actor should never ask users to paste a Facebook session. Coverage on public
pages is high without one (87–94% in our test runs). For login-gated content, use the
[`fbgql` CLI/library](https://github.com/bsho5/fbgql) locally with your own session.

**Can I scrape a single post?**
Yes — pass the post URL as `pageOrUrl`.

**Why fewer comments than Facebook shows?**
Facebook's count includes deleted/hidden/deeply nested comments the API won't return.

**Why did a run fail with a login wall?**
The target isn't publicly visible, or the IP is blocked. Enable/rotate the residential
proxy and retry.

**Can I run this completely free?**
On Apify, platform usage always applies (though the free plan covers small runs). For
**zero platform cost**, clone [github.com/bsho5/fbgql](https://github.com/bsho5/fbgql)
and run locally.

## Legal and data protection

Facebook comments contain personal data (author names). Automated scraping may breach
Facebook's Terms of Service. You are responsible for having a lawful basis for the
data you collect. See [LEGAL.md](https://github.com/bsho5/fbgql/blob/master/LEGAL.md).

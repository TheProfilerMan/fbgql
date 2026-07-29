# Facebook Page Posts & Comments Scraper — free, no login, no cookies

**Free Facebook page posts & comments scraper.** Paste a Page URL or handle — takes
N recent public posts (`maxPosts`) and scrapes each post's comments and replies.
Also groups, profiles, and single post URLs. No login. **$0 developer fee; only
Apify platform usage.**

> Looking for a **free Facebook page posts & comments scraper**? Paste a Page URL,
> set `maxPosts`, export posts + comments as JSON/CSV. No login. **$0 developer
> fee; only Apify platform usage.**

## What can this free Facebook page posts & comments scraper do?

- **Scrape comments and replies** from public **Pages**, **user profiles**, **Groups**,
  or a single **post URL**
- **No login** — no cookies, no account, no session to maintain
- **Paginate comments to exhaustion**, not just the first page
- **Stream results** to the dataset as each post finishes
- **Export** to CSV, Excel, JSON, or pull via Apify API
- **Schedule** runs, monitor failures, and integrate with Zapier/Make/n8n
- **High comment coverage** on public threads (see [coverage](#comment-coverage-and-rate-limits))

## Supported targets

| Target | Example `pageOrUrl` | Notes |
|--------|---------------------|-------|
| **Page** | `ronaldo`, `facebook`, `https://www.facebook.com/ronaldo` | Public Page timeline |
| **Profile** | `mohamed.ayuop.5` or numeric id `100003173681397` | Only if the profile is visible logged out; some handles need the numeric id |
| **Group** | `https://www.facebook.com/groups/2693577247594660` | Public groups only |
| **Post** | `https://www.facebook.com/.../posts/...` or `/permalink/...` | Scrapes that thread only (`maxPosts` ignored) |

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

- **Brand monitoring** — track what people say on your Facebook page or public group
- **Sentiment analysis** — export comment text for NLP pipelines
- **Competitive research** — scrape public competitor page/group threads
- **Market research** — collect audience reactions on viral posts
- **LLM training data** — public comment threads as structured text

## How to use this free Facebook page posts & comments scraper on Apify

### Quick start

1. Click **Try for free** / **Run**
2. Set **Page, profile, group, or post URL** — e.g. `facebook`, a profile handle, a
   `/groups/...` link, or a full post permalink
3. Leave the defaults (residential proxy on) or set `maxPosts: 5` for a page feed
4. Start the run — results stream into the **Dataset** tab as each post finishes

Default input:

```json
{ "pageOrUrl": "facebook", "maxPosts": 5 }
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
| Quick test — 1 page post + comments | `{"pageOrUrl": "facebook", "maxPosts": 1}` | Verify the scraper works |
| Scrape last 5 page posts + comments | `{"pageOrUrl": "yourbrand", "maxPosts": 5}` | Daily brand monitoring |
| Scrape public group posts + comments | `{"pageOrUrl": "https://www.facebook.com/groups/123...", "maxPosts": 3}` | Group discussion threads |
| Public profile | `{"pageOrUrl": "some.public.profile", "maxPosts": 1}` | Profile posts (if visible logged out) |
| Scrape one Facebook post comments thread | `{"pageOrUrl": "https://www.facebook.com/.../posts/..."}` | Deep-dive one thread |
| Export 10 page posts + comments for sentiment | `{"pageOrUrl": "competitor", "maxPosts": 10, "profile": "default"}` | Research export |

Pre-made configs live in [`.actor/task-examples/`](.actor/task-examples/) (when developing
from `apify/`) and [`.actor/task-examples/`](../.actor/task-examples/) (repo-root actor
definition) — same files, kept in sync.

## Is this Facebook page posts & comments scraper free?

**Yes — free.** **$0 developer fee; only Apify platform usage.** No rental and no
pay-per-result markup from the developer.

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
| `pageOrUrl` | yes | Page/profile handle, group URL, numeric id, or a single post URL |
| `maxPosts` | no | Max recent posts when scraping a feed (default 1; ignored for post URLs) |
| `proxyConfiguration` | no | Apify residential proxy, sticky per run (on by default) — **set country** if runs return 0 posts |
| `profile` | no | `default` (recommended), `tops_only`, `full_replies` |
| `engine` | no | `async` (default, streaming) or `threads` |
| `workers`, `replyFbCap`, `minIntervalSec`, `megaThreshold` | no | Advanced tuning |

## What it can and cannot reach

Because the Actor is logged out, it sees exactly what any anonymous visitor sees:

- ✅ Public **Page** posts, comments, and one level of replies
- ✅ Public **profile** posts (when Facebook embeds the profile id in logged-out HTML)
- ✅ Public **Group** posts and comments
- ✅ Individual public **post** URLs
- ❌ Private groups and private / login-gated profiles
- ❌ Age-gated or geo-restricted posts

## Troubleshooting

| Symptom | Likely cause | What to try |
|---------|--------------|-------------|
| **0 posts** / run fails with “No posts found” | Proxy IP/country blocked or empty feed from that exit | In **Proxy**, set **Apify Proxy country** to the audience’s country (or yours). Retry another country. Keep **RESIDENTIAL** on. |
| Works locally, fails on Apify | Different IP path (home vs residential exit) | Same as above — match proxy country; do not turn proxy off on the platform long-term |
| `Could not resolve numeric id` | Handle is login-gated anonymously | Pass the **numeric profile/group id**, or a direct **post URL**; or use the [`fbgql` CLI](https://github.com/bsho5/fbgql) with cookies locally |
| Login wall / `SessionInvalid` | Target private, or IP flagged | Rotate residential proxy / country; confirm the target is public in a private browser window |
| Fewer comments than Facebook shows | Deleted/hidden/nested comments | Normal — check per-post `coverage` |
| Very slow / expensive run | Huge comment threads | Start with `maxPosts: 1`, use `tops_only`, raise `minIntervalSec` |

### Proxy tips (most common fix)

1. Leave **Use Apify Proxy** + **RESIDENTIAL** enabled.
2. Set **Country** to where the Page/group’s audience (or you) sits — wrong exits often return empty feeds even when the target is public.
3. Re-run with `maxPosts: 1` after changing country before scaling up.

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
Yes — free. $0 developer fee; only Apify platform usage (compute + proxy).

**Is this a free Facebook scraper (posts + comments)?**
Yes for public content — each dataset item includes the post and its comment thread.
Free. $0 developer fee; only Apify platform usage.

**Do I need a Facebook account?**
No. The Actor scrapes public content logged out and never asks for credentials.

**Why don't you accept cookies?**
A public Actor should never ask users to paste a Facebook session. Coverage on public
targets is high without one (87–94% in our page test runs). For login-gated content, use
the [`fbgql` CLI/library](https://github.com/bsho5/fbgql) locally with your own session.

**Can I scrape a single post?**
Yes — pass the post URL as `pageOrUrl`.

**Can I scrape a public group?**
Yes — pass the full `https://www.facebook.com/groups/...` URL (or the numeric group id).

**Why fewer comments than Facebook shows?**
Facebook's count includes deleted/hidden/deeply nested comments the API won't return.

**Why did a run fail with a login wall or “No posts found”?**
The target isn't publicly visible from that IP, or the proxy country is a bad fit. Change
the residential proxy country and retry — see [Troubleshooting](#troubleshooting).

**Can I run this completely free?**
On Apify, platform usage always applies (though the free plan covers small runs). For
**zero platform cost**, clone [github.com/bsho5/fbgql](https://github.com/bsho5/fbgql)
and run locally.

## Legal and data protection

Facebook comments contain personal data (author names). Automated scraping may breach
Facebook's Terms of Service. You are responsible for having a lawful basis for the
data you collect. See [LEGAL.md](https://github.com/bsho5/fbgql/blob/master/LEGAL.md).

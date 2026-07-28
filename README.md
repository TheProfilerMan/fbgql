# fbgql

Clean-room Facebook **GraphQL** post & comment scraper — usable as a **library**, a
**CLI**, and a **public Apify actor**. One engine, many callers.

> Working name `fbgql` — rename before publishing. Proprietary/clean-room: see
> [`LICENSE`](LICENSE) and [`LEGAL.md`](LEGAL.md).

## What it does

Given a Facebook page (or a single post URL), it fetches recent posts and paginates
their comments + one level of replies via the private GraphQL API, using the proven
coverage policy:

- permalink `feedLocation` (`POST_PERMALINK_DIALOG`)
- `1675012` empty-page retry with backoff
- no artificial page cap
- bin-packed multi-worker runner with a configurable reply cap

## Two access modes — anonymous is the default

| Mode | How | Reach |
|---|---|---|
| **anonymous** (default) | pass no account — actor `0`, no cookies, no `fb_dtsg` | public content only |
| **authenticated** | supply cookies (`--cookies` / `Account(cookies=…)`) | everything the account can see |

Facebook's GraphQL endpoint answers public timeline, comment, and reply queries to a
logged-out actor, so page discovery, full comment pagination, and replies all work with
no account at all — no browser, no login, no token bootstrap:

```bash
fbgql scrape --page facebook --posts 3           # anonymous; nothing to set up
fbgql scrape --page facebook --cookies c.json    # authenticated, for gated content
```

Reference runs on the same page and post count: **93.5% weighted coverage anonymous**
(20 posts, 2 817 comments, 0 errors) against a documented **77.1% authenticated**
baseline. The two were measured on different days against different posts, so read that
as "anonymous is in the same class or better on public pages", not a controlled result.

Anonymous is the default because it removes the operational bottleneck: there is no
`c_user` to checkpoint, so a block costs a retry instead of a session, and scale depends
on IP diversity rather than on a supply of healthy accounts.

**Supplying an account whose cookies lack `c_user` is still a hard failure** — that is a
dead session, not an anonymous one, and it must not silently degrade. Anonymous applies
when you pass *no* account (or set `anonymous=True` explicitly).

Login-gated, age-gated, and geo-restricted content and private groups stay unreachable
anonymously — use authenticated mode for those.

Measured, mechanism, and limits: [`reports/ANONYMOUS_ACCESS_SOLVED_2026-07-28.md`](reports/ANONYMOUS_ACCESS_SOLVED_2026-07-28.md).

## Two engines (pick per job)

| `engine` | Backend | When |
|----------|---------|------|
| `"threads"` (default) | `ThreadPoolExecutor` + `requests` | Proven, reproduces measured coverage |
| `"async"` | `asyncio` + `httpx` | Streaming, native fit for the Apify actor |

Both share all decision logic (payloads, parsing, retry policy, bin-packing); only
the I/O loop differs.

## Quickstart (one command)

`run.sh` does everything — picks Python 3.11+, creates the venv, installs, then scrapes.
The default path is anonymous, so it needs **no browser and no login**:

```bash
# Quickest first run — 1 post, top-level comments only
PROFILE=tops_only ./run.sh facebook 1

./run.sh                  # scrape the default page (PAGE/POSTS defaults), logged out
./run.sh <page> 30        # page + post count
./run.sh doctor           # check doc_ids still resolve

AUTH=1 ./run.sh           # authenticated instead (mints cookies if needed)
./run.sh login            # just mint/refresh cookies
```

Override via env: `PAGE=… POSTS=… PROFILE=… ENGINE=… OUT=… PROXY=… ./run.sh`.
Only `AUTH=1`, `login`, and `capture` need a display for the browser step; the default
anonymous path runs fine in containers.

**Budget the run time.** Comments are paginated to exhaustion, so wall-clock scales with
how busy the target is, not with post count alone. Measured on `facebook` (Meta's own
page, ~1 000 comments/post): **~5 min per post** on the `default` profile. Busy pages are
where `tops_only`, `--reply-cap`, and a lower `--posts` earn their keep.

## Install

```bash
pip install -e .            # core (library + CLI)
pip install -e ".[dev]"     # + ruff, pytest
pip install -e ".[mint]"    # + selenium, for the interactive login helper
pip install -e ".[apify]"   # + apify SDK
```

## Library

```python
from fbgql import Scraper, ScrapeJob, Account, Profile

# Anonymous (default) — no accounts needed
job = ScrapeJob(
    page="facebook",
    max_posts=3,
    profile=Profile.DEFAULT,     # DEFAULT | TOPS_ONLY | FULL_REPLIES
    engine="threads",            # or "async"
)

# Authenticated — supply a session for login-gated content
job = ScrapeJob(
    page="facebook",
    max_posts=3,
    accounts=[Account(cookies=cookies_dict, proxy="http://user:pass@host:port")],
)

result = Scraper().run(job)
result.to_json("out/result.json")

# streaming (threads):
for post in Scraper().stream(job):
    ...
```

The engine **never logs in** — anonymous runs as actor `0`, and authenticated runs
consume cookies you supply. With cookies, `fb_dtsg` is derived at runtime; a dead
session raises `SessionInvalid` so a wrapper can alert a human to re-mint. See "Auth"
below.

## CLI

```bash
# Anonymous (default)
fbgql scrape --page facebook --posts 3 --profile default \
  --engine threads --out out/result.json

# Authenticated
fbgql scrape --page facebook --posts 3 --cookies cookies.json --out out/result.json

fbgql doctor --page facebook            # check doc_ids are still valid (logged out)
fbgql mint-session --out cookies.json   # interactive login (needs [mint] extra)
```

## Auth (how login works)

Most runs need none — anonymous is the default and requires no credentials at all.

When you do want authenticated reach, you never log in on a server. You mint cookies
**once** on a machine with a browser and a residential IP (`fbgql mint-session`), then
inject that `cookies.json` as a secret wherever you run — CLI, Docker, or VPS. The
scraper derives `fb_dtsg` from those cookies over plain HTTP (no browser at scrape time).

The **Apify actor takes no credentials at all** — it is anonymous-only by design, since a
public actor should never ask users to paste a Facebook session into its input.

## Consuming from a separate repo (backend wrapper)

```toml
# your wrapper's pyproject.toml
dependencies = ["fbgql @ git+https://github.com/bsho5/fbgql.git@v0.1.0"]
```

The monorepo layout (core + `apify/` actor) does not constrain consumers — pip
installs only `src/fbgql/`.

## Layout

```
src/fbgql/          core engine (library + CLI)
apify/              public Apify Store actor (thin adapter)
docker/             generic CLI image
tools/mint_session/ interactive login helper
examples/  tests/
```

## doc_id drift

Facebook rotates GraphQL `doc_id`s. They are treated as **config**, overridable via
`FBGQL_DOC_ID_*` env vars without a code release. `fbgql doctor` reports stale ones.

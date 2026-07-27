# fbgql

Clean-room Facebook **GraphQL** post & comment scraper — usable as a **library**, a
**CLI**, and a **public Apify actor**. One engine, many callers.

> Working name `fbgql` — rename before publishing. Proprietary/clean-room: see
> [`LICENSE`](LICENSE) and [`LEGAL.md`](LEGAL.md).

## What it does

Given a Facebook page (or a single post URL) and a valid **session (cookies)**, it
fetches recent posts and paginates their comments + one level of replies via the
private GraphQL API, using the proven coverage policy:

- permalink `feedLocation` (`POST_PERMALINK_DIALOG`)
- `1675012` empty-page retry with backoff
- no artificial page cap
- bin-packed multi-worker runner with a configurable reply cap

Reference run: **77.1% weighted coverage** on a hard page (`ZainSudan`, 20 posts).

## Two engines (pick per job)

| `engine` | Backend | When |
|----------|---------|------|
| `"threads"` (default) | `ThreadPoolExecutor` + `requests` | Proven, reproduces measured coverage |
| `"async"` | `asyncio` + `httpx` | Streaming, native fit for the Apify actor |

Both share all decision logic (payloads, parsing, retry policy, bin-packing); only
the I/O loop differs.

## Quickstart (one command)

On a machine with a browser, `run.sh` does everything — picks Python 3.11+, creates
the venv, installs, mints cookies **only if missing/expired** (opens a browser), then
scrapes:

```bash
./run.sh                  # scrape the default page
./run.sh SudaniTV 30      # page + post count
./run.sh login            # just mint/refresh cookies
./run.sh doctor           # check session + doc_ids
```

Override via env: `PAGE=… POSTS=… PROFILE=… ENGINE=… COOKIES=… OUT=… PROXY=… ./run.sh`.
In containers / Apify you inject cookies instead (headless browser login is
unreliable) — see below.

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

job = ScrapeJob(
    page="ZainSudan",
    max_posts=20,
    profile=Profile.DEFAULT,     # DEFAULT | TOPS_ONLY | FULL_REPLIES
    engine="threads",            # or "async"
    accounts=[Account(cookies=cookies_dict, proxy="http://user:pass@host:port")],
)

result = Scraper().run(job)
result.to_json("out/result.json")

# streaming (threads):
for post in Scraper().stream(job):
    ...
```

The engine **never logs in** — it consumes cookies. `fb_dtsg` is derived from the
cookies at runtime; a dead session raises `SessionInvalid` so a wrapper can alert a
human to re-mint. See "Auth" below.

## CLI

```bash
fbgql scrape --page ZainSudan --posts 20 --profile default \
  --engine threads --cookies cookies.json --out out/result.json

fbgql doctor --cookies cookies.json     # check doc_ids are still valid
fbgql mint-session --out cookies.json   # interactive login (needs [mint] extra)
```

## Auth (how login works)

You never log in on a server. You mint cookies **once** on a machine with a browser
and a residential IP (`fbgql mint-session`), then inject that `cookies.json` as a
secret wherever you run — CLI, Docker, VPS, or Apify. The scraper derives `fb_dtsg`
from those cookies over plain HTTP (no browser at scrape time).

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

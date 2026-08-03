---
name: fbgql-refresh-doc-ids
description: >-
  Refresh Facebook GraphQL doc_ids and required Relay provider variables for
  fbgql (timeline, group_feed, comments, replies) when Meta rotates persisted
  queries. Use when scrapes return empty pages, missing_required_variable_value,
  DocIdStale, error 1675012 with no edges, or the user asks to capture/refresh
  doc_ids, update GraphQL query ids, or fix stale Facebook GraphQL payloads.
---

# Refresh fbgql Facebook GraphQL doc_ids

Facebook rotates persisted GraphQL `doc_id`s. Symptoms: empty timeline/comments,
`missing_required_variable_value`, or `1675012` with **no** edges (not a transient
empty-page retry). Fix = capture live browser queries → apply into `config.py` →
verify with `doctor`.

**Do this fast. Do not reverse-engineer payloads by hand.**

## Preconditions

- Work in the `fbgql` repo root (or set `FBGQL_ROOT`).
- Valid session cookies preferred (`cookies.json`). Capture can mint interactively.
- Needs Chrome + `[mint]` extra: `pip install -e ".[mint]"`

## Fast path (default)

Copy and track:

```
Refresh Progress:
- [ ] 1. doctor (confirm stale)
- [ ] 2. capture live queries
- [ ] 3. apply into config.py
- [ ] 4. doctor again (must pass)
- [ ] 5. optional: smoke scrape 1 post
```

### 1. Confirm stale

```bash
cd "${FBGQL_ROOT:-.}"
./run.sh doctor
# or:
.venv/bin/fbgql doctor --cookies cookies.json --page ZainSudan
```

Stale signals: `doc_id:*` checks fail, or scrape logs `missing_required_variable_value`.

### 2. Capture (browser)

```bash
./run.sh capture ZainSudan
# or:
.venv/bin/fbgql capture --page ZainSudan --cookies cookies.json --out captured_queries.json
```

- Opens a real browser; injects cookies if present.
- Scrolls the page feed, opens one post, scrolls comments.
- Writes `captured_queries.json` with `resolved.timeline|group_feed|comments|replies`.

If a logical name prints `NOT captured`, re-run capture on a page that triggers it
(e.g. a **group** URL for `group_feed`, a post with reply threads for `replies`).

### 3. Apply into shipped defaults

```bash
python .cursor/skills/fbgql-refresh-doc-ids/scripts/apply_doc_ids.py \
  --capture captured_queries.json \
  --config src/fbgql/config.py
```

The script updates:

| Target in `config.py` | Source |
|---|---|
| `_DEFAULT_DOC_IDS[...]` | `resolved.*.doc_id` |
| `TIMELINE_VARIABLES_BASE` `__relay_internal__*` keys | `resolved.timeline.variables` |
| `GROUP_FEED_VARIABLES_BASE` `__relay_internal__*` keys | `resolved.group_feed.variables` |
| `UFI_COMMENT_PROVIDER_VARS` | `__relay_internal__*` from comments (fallback replies) |

Runtime override without editing code (hot-swap):

```bash
export FBGQL_DOC_ID_COMMENTS=...
export FBGQL_DOC_ID_REPLIES=...
export FBGQL_DOC_ID_TIMELINE=...
export FBGQL_DOC_ID_GROUP_FEED=...
```

Prefer applying to `config.py` for a durable fix; use env vars for a one-off probe.

### 4. Re-verify

```bash
./run.sh doctor
```

All `doc_id:*` checks should pass.

### 5. Optional smoke

```bash
POSTS=1 PROFILE=tops_only ./run.sh ZainSudan
```

Expect `total_scraped > 0` (or a clear non-doc_id error like checkpoint).

## Also update legacy compare tree (only if user asks)

If still using `_compare_mohdtalal3`:

| File | Field |
|---|---|
| `post_scraper.py` | `DOC_ID` ← `resolved.timeline.doc_id` |
| `comment_scraper.py` | comments `doc_id` ← `resolved.comments.doc_id` |
| `comment_scraper.py` | replies `doc_id` ← `resolved.replies.doc_id` |

Prefer `fbgql` going forward; do not invent compare-only capture paths.

## Failure triage

| Symptom | Action |
|---|---|
| Capture `NOT captured` for comments/replies | Open a post with visible comments; increase scrolls; ensure logged in |
| Capture empty / checkpoint URL | Re-mint cookies (`./run.sh login`); cool restricted account |
| Apply reports no changes | Capture `resolved` empty — re-capture |
| Doctor still fails after apply | Diff captured variables vs `*_VARIABLES_BASE` / `UFI_COMMENT_PROVIDER_VARS`; missing `__relay_internal__pv__*` is the usual gap |
| Soft `WARNING` + edges present | OK — not stale; do not refresh |

## Do not

- Guess new doc_ids from old digests or random Meta build numbers.
- Retry `1675012` forever when the message is `missing_required_variable_value` on page 1 (that is stale query, not transient empty).
- Commit `cookies.json` or live session secrets.

## References

- Capture implementation: `src/fbgql/capture.py`
- Registry / defaults: `src/fbgql/config.py`
- CLI: `fbgql capture`, `fbgql doctor`
- Apply helper: [scripts/apply_doc_ids.py](scripts/apply_doc_ids.py)

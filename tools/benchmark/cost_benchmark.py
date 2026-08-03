"""TRUE wire-byte measurement: urllib3 tracks pre-decompression bytes read from the
socket in HTTPResponse._fp_bytes_read. That is what a metered proxy actually bills."""
import sys, time, json, threading

import requests

WIRE = 0
DECOMP = 0
UP = 0
REQS = 0
MISSING = 0
_lock = threading.Lock()

_orig_post = requests.Session.post
_orig_get = requests.Session.get


def _measure(resp, sent):
    global WIRE, DECOMP, UP, REQS, MISSING
    body = resp.content
    raw = getattr(resp, "raw", None)
    n = getattr(raw, "_fp_bytes_read", None)
    if n is None:
        n = len(body)
        with _lock:
            MISSING += 1
    hdr = sum(len(k) + len(v) + 4 for k, v in resp.headers.items())
    with _lock:
        WIRE += n + hdr
        DECOMP += len(body)
        UP += sent
        REQS += 1


def _sent(kw):
    n = 0
    data = kw.get("data")
    if isinstance(data, dict):
        n += sum(len(str(k)) + len(str(v)) + 2 for k, v in data.items())
    elif data:
        n += len(data)
    for key in ("headers", "cookies"):
        n += sum(len(str(k)) + len(str(v)) + 4 for k, v in (kw.get(key) or {}).items())
    return n


def post(self, url, **kw):
    r = _orig_post(self, url, **kw)
    _measure(r, _sent(kw))
    return r


def get(self, url, **kw):
    r = _orig_get(self, url, **kw)
    _measure(r, _sent(kw))
    return r


requests.Session.post = post
requests.Session.get = get

from fbgql import Scraper, ScrapeJob, Profile  # noqa: E402

page = sys.argv[1] if len(sys.argv) > 1 else "ronaldo"
posts = int(sys.argv[2]) if len(sys.argv) > 2 else 1

t0 = time.time()
result = Scraper().run(ScrapeJob(page=page, max_posts=posts,
                                 profile=Profile.DEFAULT, engine="threads"))
dt = time.time() - t0
d = json.loads(json.dumps(result, default=lambda o: getattr(o, "__dict__", str(o))))
plist = d.get("posts") or d.get("results") or []
total = sum(p.get("total_scraped", 0) for p in plist)

tb = WIRE + UP
gb = tb / 1e9
proxy = gb * 8.0
cu = 1.0 * dt / 3600
compute = cu * 0.20
cost = proxy + compute
inc = total * 0.0025 + 0.006

print("\n" + "=" * 72)
print(f"target              : {page}  posts={posts}")
print(f"wall clock          : {dt:,.1f} s   requests: {REQS}   (missing raw counter: {MISSING})")
print(f"WIRE bytes (billed) : {WIRE:,} ({WIRE/1e6:.2f} MB)")
print(f"decompressed        : {DECOMP:,} ({DECOMP/1e6:.2f} MB)")
print(f"compression         : {DECOMP/WIRE if WIRE else 0:.1f}x")
print(f"comments scraped    : {total:,}")
if total:
    print(f"wire KB per comment : {WIRE/total/1024:.2f} KB")
print("-" * 72)
print(f"residential proxy   : ${proxy:.4f}   (@ $8/GB)")
print(f"compute             : ${compute:.4f}   ({cu:.4f} CU @ $0.20)")
print(f"TOTAL PLATFORM COST : ${cost:.4f}")
if total:
    print(f"  our  $/comment    : ${cost/total:.7f}")
    print(f"  incumbent run cost: ${inc:.4f}   ($0.0025/comment)")
    print(f"  ADVANTAGE         : {inc/cost:.0f}x cheaper")
    print()
    print(f"  10,000 comments  -> us ${cost/total*10000:.2f}  vs incumbent ${10000*0.0025:.2f}")
    print(f"  100,000 comments -> us ${cost/total*100000:.2f} vs incumbent ${100000*0.0025:.2f}")
print("=" * 72)
json.dump({"page": page, "posts": posts, "seconds": dt, "requests": REQS,
           "wire_bytes": WIRE, "decompressed_bytes": DECOMP, "comments": total,
           "cost_usd": cost, "incumbent_usd": inc},
          open("measure_true_result.json", "w"), indent=2)

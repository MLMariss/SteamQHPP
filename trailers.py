#!/usr/bin/env python3
"""
Steam QTPD — store trailer index
===========================================================================
One SEPARATE, independent job that owns the TRAILER layer: for each appid, the
CDN filename(s) of its store trailer, so the frontend can play a video preview
when you hover a game's thumbnail.

WHY THIS NEEDS A SCRAPE AT ALL
------------------------------
Thumbnails are free: every capsule/header image URL is derivable from the appid
alone (`.../steam/apps/<appid>/header.jpg`), which is why the hover-enlarge has
never needed a data layer. Trailers are NOT. A Steam trailer lives under its own
`movie id` — 738090 (GRIT) serves its trailer from `store_trailers/257059122/...`
— and that id is not derivable from the appid by any rule. It has to be looked up
and stored. Hence: one more file, one more job (ARCHITECTURE §1, one writer per
file).

THE ENDPOINT
------------
IStoreBrowseService/GetItems/v1 with `data_request.include_trailers`. Same batched
endpoint price_and_sale.py already uses for sale end-dates, on api.steampowered.com
(the big budget, not the 200-per-5-min storefront one), 50 appids per call. A full
sweep of the ~127k catalog is ~2.5k calls ≈ 50 minutes — cheap enough that this job
is mostly idle after the first pass.

SCHEMA TOLERANCE
----------------
Same posture as price_and_sale.py's `_extract_end_date` (see its §"the various
GetItems schema revisions"): Valve reshapes these blobs without notice, and the
exact key names under `trailers` are the least documented part of the store API.
So `extract_trailer` does NOT hardcode a path. It walks the whole `trailers` blob
for any dict carrying a video `filename` and classifies by the FILENAME, whose
conventions (`movie480`, `movie_max`, `microtrailer`) have been stable for years
even as the surrounding keys moved. Set QTPD_DUMP_TRAILERS=1 to dump raw items
from a runner that can actually reach the API, then tighten if you want to.

Output trailers.json (served to the browser):
  { "base": "<cdn prefix>", "trailers": { "<appid>": [[<480p files>], [<micro files>]] } }
Filenames are relative to `base` and ordered by preference, so the frontend emits
one <source> per entry and lets the browser pick the first codec it supports.
Games with no trailer are absent — the frontend falls back to today's still image.

Output trailers_state.json (NOT served; the queue's memory, like catalog.json):
  { "misses": { "<appid>": <ts> }, "swept_at": <ts> }
A miss is re-checked after MISS_TTL_DAYS, because an unreleased game gains a
trailer later.

Ownership (one writer per file):
  scraper.py      -> games.json    (catalog, rating, tags, last_update, release)
  price_and_sale  -> prices.json   (price, discount %, sale end)
  THIS            -> trailers.json + trailers_state.json
Reads games.json (read-only) for the appid list and review counts.
"""

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"                    # read-only (owned by scraper.py)
TRAILERS_FILE = HERE / "trailers.json"              # this job's output (served)
STATE_FILE = HERE / "trailers_state.json"           # this job's queue memory (not served)

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "60"))
CHECKPOINT_SECONDS = 300
TIME_BUFFER = 45

GETITEMS_BATCH = 50                                 # appids per GetItems call
GETITEMS_DELAY = 1.2                                # matches price_and_sale.py's pacing
MAX_RETRIES = 4
MISS_TTL_DAYS = int(os.environ.get("QTPD_TRAILER_MISS_TTL", "30"))

# Fallback CDN prefix, used when no response carried a `trailer_url_format` to learn
# from. Valve has served store trailers from this host for years; the per-run learned
# value still wins so a host migration needs no code change.
DEFAULT_BASE = "https://video.akamai.steamstatic.com/store_trailers/"

VIDEO_EXTS = (".webm", ".mp4")
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
HEADERS = {"User-Agent": "Mozilla/5.0 (steam-qtpd trailer indexer; github pages dataset builder)",
           "Accept-Language": "en-US,en;q=0.9"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def log(msg):
    print(msg, flush=True)


def get(url, *, params=None, timeout=40):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = min(90, 5 * attempt)
                log(f"  429 rate-limited, sleeping {wait}s"); time.sleep(wait); continue
            if r.status_code == 403:
                log("  403 (soft-limit); cooling down 60s"); time.sleep(60); continue
            r.raise_for_status()
            try:
                return r.json()
            except ValueError:
                return None
        except requests.RequestException as e:
            wait = min(30, 3 * attempt)
            log(f"  request error ({attempt}/{MAX_RETRIES}): {e}; retry in {wait}s")
            time.sleep(wait)
    return None


# --------------------------------------------------------------------------- #
# Trailer extraction — filename-driven, not key-path-driven (see module docstring)
# --------------------------------------------------------------------------- #
def _walk(node):
    """Yield every dict nested anywhere under `node` (any depth, through lists)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _rank(filename):
    """Codec preference within one tier: VP9/WebM first (roughly half the bytes of
    the h264 mp4 at the same tier, and every browser we care about plays it except
    old Safari), mp4 second as the compatibility source."""
    f = filename.lower()
    if f.endswith(".webm"):
        return 0
    return 1


def extract_trailer(item):
    """(list_480p, list_micro, base_or_None) for one GetItems store_item.

    Both lists are CDN-relative filenames ordered best-codec-first; either may be
    empty. Classification is by filename because that is the stable part:

      movie480_vp9.webm / movie480.mp4   -> the 480p tier, what we actually play
      movie_max_vp9.webm / movie_max.mp4 -> source tier; used ONLY if no 480 exists
      microtrailer.webm                  -> Valve's own ~6s silent loop

    Anything else that ends .webm/.mp4 is kept as a last-resort 480p candidate, so a
    renamed tier still yields a playable URL instead of nothing.
    """
    trailers = item.get("trailers")
    if not isinstance(trailers, (dict, list)):
        return [], [], None

    base = None
    tier480, tiermax, micro, other = [], [], [], []
    for d in _walk(trailers):
        if base is None:
            # The prefix normally arrives as `trailer_url_format`, but that key has been
            # renamed before, so match on the VALUE instead: any string holding a
            # store_trailers URL with a {PLACEHOLDER}. Strip the placeholder to leave a
            # plain prefix we can concatenate against.
            for v in d.values():
                if isinstance(v, str) and "{" in v and "store_trailers" in v:
                    base = v.split("{")[0]
                    break
        fn = d.get("filename")
        if not isinstance(fn, str):
            continue
        low = fn.lower()
        if not low.endswith(VIDEO_EXTS):
            continue
        if "microtrailer" in low:
            micro.append(fn)
        elif "480" in low:
            tier480.append(fn)
        elif "max" in low:
            tiermax.append(fn)
        else:
            other.append(fn)

    # Dedupe while keeping the codec ordering deterministic.
    def _clean(xs):
        return sorted(dict.fromkeys(xs), key=_rank)

    play = _clean(tier480) or _clean(tiermax) or _clean(other)
    return play, _clean(micro), base


# --------------------------------------------------------------------------- #
# GetItems
# --------------------------------------------------------------------------- #
def getitems(appids):
    """One batched GetItems call -> list of store_item dicts (empty list on failure)."""
    payload = {
        "ids": [{"appid": int(a)} for a in appids],
        "context": {"country_code": os.environ.get("QHPP_CC", "US"), "language": "english"},
        # include_trailers is the only block this job needs; basic_info stays on purely
        # so the response echoes an identifiable appid per item. Everything else off.
        "data_request": {"include_basic_info": True, "include_trailers": True,
                         "include_assets": False, "include_release": False,
                         "include_tag_count": 0, "include_reviews": False,
                         "include_platforms": False, "include_all_purchase_options": False},
    }
    params = {"input_json": json.dumps(payload, separators=(",", ":"))}
    if STEAM_API_KEY:
        params["key"] = STEAM_API_KEY
    data = get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/", params=params)
    if not isinstance(data, dict):
        return []
    items = ((data.get("response") or {}).get("store_items")) or []
    # Diagnostic twin of price_and_sale.py's QHPP_DUMP_GETITEMS: set QTPD_DUMP_TRAILERS=1
    # and run the workflow manually to see the real shape from a runner that can actually
    # reach the API (a sandbox with Steam blocked cannot).
    if os.environ.get("QTPD_DUMP_TRAILERS") == "1":
        log("=== RAW GetItems(trailers) DUMP (first 3 items) ===")
        for it in items[:3]:
            log(json.dumps(it.get("trailers"), indent=2)[:4000])
            log("---")
        log("=== extract_trailer results: "
            f"{[(it.get('appid') or it.get('id'), extract_trailer(it)[:2]) for it in items[:10]]}")
        sys.exit(0)
    return items


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #
def load_catalog():
    """[(appid, review_count)] from games.json, most-reviewed first.

    Ordering is the whole first-pass strategy: the backlog is ~127k games but the
    ones anybody actually hovers are the popular ones, so trailers show up on the
    games that matter within the first run rather than after the full sweep.
    """
    if not GAMES_FILE.exists():
        return []
    try:
        d = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if d.get("sample"):
        return []
    rows = [(int(g["appid"]), int(g.get("review_count") or 0))
            for g in d.get("games", []) if g.get("appid") is not None]
    rows.sort(key=lambda r: -r[1])
    return rows


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default


def save_trailers(hits, base):
    # Compact separators, not indent=2: this file is machine-generated, browser-facing,
    # and ~100k rows deep — pretty-printing it would roughly triple the bytes on the
    # wire for zero human benefit.
    TRAILERS_FILE.write_text(json.dumps(
        {"format": "trailers_v1", "generated_at": int(time.time()),
         "base": base, "count": len(hits),
         "trailers": {str(k): v for k, v in sorted(hits.items(), key=lambda kv: int(kv[0]))}},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def save_state(misses, swept_at):
    STATE_FILE.write_text(json.dumps(
        {"generated_at": int(time.time()), "swept_at": swept_at,
         "misses": {str(k): v for k, v in sorted(misses.items(), key=lambda kv: int(kv[0]))}},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def git_checkpoint(msg):
    if not IN_ACTIONS:
        return
    try:
        subprocess.run(["git", "add", "trailers.json", "trailers_state.json"], check=False)
        if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode != 0:
            subprocess.run(["git", "commit", "-m", msg], check=False)
            for _attempt in range(1, 9):    # retry against other jobs pushing concurrently
                subprocess.run(["git", "fetch", "origin", "main"], check=False)
                subprocess.run(["git", "rebase", "--autostash", "origin/main"], check=False)
                if subprocess.run(["git", "push", "origin", "HEAD:main"],
                                  capture_output=True, text=True).returncode == 0:
                    log(f"  committed: {msg}")
                    break
                time.sleep(2 * _attempt + random.uniform(0, 2))
    except Exception as e:
        log(f"  git checkpoint failed: {e}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def select_work(catalog, hits, misses, now):
    """Appids to query this run: never-checked first (most-reviewed first), then
    stale misses (oldest first). A hit is never re-queried — a trailer's movie id is
    effectively permanent, and the periodic full re-sweep is a manual dispatch."""
    ttl = MISS_TTL_DAYS * 86400
    fresh, stale = [], []
    for appid, _rc in catalog:
        key = str(appid)
        if key in hits:
            continue
        seen = misses.get(key)
        if seen is None:
            fresh.append(appid)
        elif (now - int(seen)) >= ttl:
            stale.append((int(seen), appid))
    stale.sort()
    return fresh + [a for _ts, a in stale]


def main():
    started = time.time()
    deadline = started + RUN_MINUTES * 60 - TIME_BUFFER

    catalog = load_catalog()
    if not catalog:
        log("games.json missing or sample-only — nothing to do.")
        return

    tdoc = load_json(TRAILERS_FILE, {})
    hits = dict(tdoc.get("trailers") or {})
    base = tdoc.get("base") or DEFAULT_BASE
    sdoc = load_json(STATE_FILE, {})
    misses = dict(sdoc.get("misses") or {})
    swept_at = sdoc.get("swept_at") or 0

    queue = select_work(catalog, hits, misses, int(time.time()))
    log(f"Catalog {len(catalog)} | have trailers {len(hits)} | known misses {len(misses)} | "
        f"queued {len(queue)} | budget {RUN_MINUTES}min")
    if not queue:
        log("Nothing due. (Trailer ids are permanent; re-sweep via manual dispatch.)")
        save_state(misses, int(time.time()))
        git_checkpoint("trailers: nothing due")
        return

    last_ckpt = time.time()
    found = checked = 0
    for i in range(0, len(queue), GETITEMS_BATCH):
        if time.time() >= deadline:
            log("  time budget reached — wrapping up")
            break
        batch = queue[i:i + GETITEMS_BATCH]
        items = getitems(batch)
        time.sleep(GETITEMS_DELAY)
        now = int(time.time())
        seen_ids = set()
        for it in items:
            aid = it.get("appid") or it.get("id")
            if aid is None:
                continue
            key = str(aid)
            seen_ids.add(int(aid))
            play, micro, learned = extract_trailer(it)
            if learned:
                base = learned
            if play or micro:
                hits[key] = [play, micro]
                misses.pop(key, None)
                found += 1
            else:
                misses[key] = now
        # Appids the response dropped entirely (delisted, region-locked, not an app):
        # record them as misses so they don't re-queue every single run.
        for aid in batch:
            if int(aid) not in seen_ids and str(aid) not in hits:
                misses[str(aid)] = now
        checked += len(batch)

        if time.time() - last_ckpt >= CHECKPOINT_SECONDS:
            save_trailers(hits, base)
            save_state(misses, swept_at)
            git_checkpoint(f"trailers: {len(hits)} with video ({found} new this run)")
            last_ckpt = time.time()

    if checked >= len(queue):
        swept_at = int(time.time())
    save_trailers(hits, base)
    save_state(misses, swept_at)
    git_checkpoint(f"trailers: {len(hits)} with video ({found} new this run)")
    log(f"Done. checked {checked}, found {found}, total with trailers {len(hits)}, "
        f"misses {len(misses)} | {(time.time()-started)/60:.1f}min")


if __name__ == "__main__":
    main()

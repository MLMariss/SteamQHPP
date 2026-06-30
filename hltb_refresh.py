#!/usr/bin/env python3
"""
Steam QHPP — HowLongToBeat refresher
====================================
A SEPARATE, independent job from scraper.py, for the same reason recent/sales were
split out: HLTB lookups are the SLOWEST part of the whole pipeline. The howlongtobeatpy
library scrapes howlongtobeat.com, and each search is a 2-10s (sometimes hanging)
round-trip with no rate budget. When that ran inside the main scrape loop it dominated
per-game time — the scraper was doing ~6 games/min when Steam itself would allow ~40,
because every new game waited on an HLTB search. Pulling HLTB out makes the main scrape
~3-5x faster instantly.

Why a separate cadence works well here: HLTB completion times are mostly STATIC — a
game's "how long to beat" changes slowly, if at all. The first pass fills hltb.json for
games that don't have an entry yet (the priority). Once that pass is complete, leftover
budget goes to a RE-SCRAPE pass that revisits existing entries on staleness windows
(partials soonest, blanks rarely, full triples almost never — see T5), to pick up data
HLTB added after our first lookup. It can run slowly in the background without holding
anything up.

Ownership (one writer per file, no push collisions):
  scraper.py      -> games.json   (catalog, rating, tags, last_update, release)
  price_and_sale  -> prices.json  (price, discount, sale end)
  THIS            -> hltb.json     {appid: {main, extra, complete, avg, match}}
  recent_refresh  -> recent.json  (30-day review scores)
The frontend merges all of these by appid; QHPP is computed client-side from the merge.

Reads games.json (read-only) just to know which appids exist and their titles (HLTB
matches by title, not appid).
"""

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import hltb_estimate as HE      # shared fill logic (live median ratio + missing-value fill)

try:
    from howlongtobeatpy import HowLongToBeat
except ImportError:
    HowLongToBeat = None

HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"          # read-only (owned by scraper.py)
HLTB_FILE = HERE / "hltb.json"            # this job's output (committed)

RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "120"))
CHECKPOINT_SECONDS = 300
TIME_BUFFER = 45
HLTB_MIN_SIMILARITY = 0.65
HLTB_DELAY = 0.6                          # pacing between HLTB searches (howlongtobeat tolerates this)

# Re-scrape staleness gates (T5). Once the first pass is done (no never-seen games left),
# the job re-fetches EXISTING entries with leftover budget, oldest-first within each bucket,
# but only if an entry hasn't been refetched within its bucket's window. This stops any one
# title being re-hit every run while still letting incomplete/blank entries pick up data
# HLTB added later. Yield drives the cadence: partials (HLTB already has the page, missing
# fields fill in) are high-value and retried often; blanks are mostly irreducible (HLTB has
# no page) so retried rarely; full triples almost never change, so almost never.
RESCRAPE_PARTIAL_DAYS = 14               # entries with 1-2 real raw values
RESCRAPE_BLANK_DAYS = 60                 # no-match entries (0 real raw values)
RESCRAPE_FULL_DAYS = 365                 # complete triples (3 real raw values)
DAY = 86400
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def log(msg):
    print(msg, flush=True)


def hltb_for(title):
    """Fetch best-match HLTB times for a title. Returns a dict of RAW values:
    {"main", "extra", "complete", "match"} — zeros/missing as None, NO estimation
    and NO avg here (the shared estimator fills + averages at storage time). A
    genuine no-match returns the raw blank (recorded so we don't re-search it
    every run during the first pass). A transient error returns None (leave
    unresolved, retry next run)."""
    blank = {"main": None, "extra": None, "complete": None, "match": None}
    if HowLongToBeat is None:
        return blank
    try:
        results = HowLongToBeat().search(title)
    except Exception as e:
        log(f"  HLTB error '{title}': {e}")
        return None                       # transient -> don't record, retry next run
    if not results:
        return blank                      # genuinely no match -> record blank (don't re-search forever)
    best = max(results, key=lambda r: r.similarity or 0)
    if (best.similarity or 0) < HLTB_MIN_SIMILARITY:
        return blank

    def hrs(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return round(v, 1) if v > 0 else None

    return {"main": hrs(best.main_story), "extra": hrs(best.main_extra),
            "complete": hrs(best.completionist), "match": best.game_name}


def rescrape_bucket(entry):
    """Classify an existing hltb entry by how many REAL (raw) values it has, which
    determines its re-scrape priority and staleness window. Returns one of
    'partial' (1-2 real), 'blank' (0 real / no-match), 'full' (3 real)."""
    rm, re_, rc = HE.raw_of(entry)
    n_real = sum(1 for x in (rm, re_, rc) if HE.is_real(x))
    if n_real >= 3:
        return "full"
    if n_real >= 1:
        return "partial"
    return "blank"


def build_rescrape_queue(games, hltb, now):
    """Build the ordered re-scrape work list from games that ALREADY have an entry.
    Priority order (highest expected yield first, matching §2 → T5): partial -> blank
    -> full. Within each bucket, oldest fetched_at first so retries spread evenly and
    no entry is re-hit twice before its peers get one pass. An entry is only eligible
    if it hasn't been refetched within its bucket's staleness window. Games with no
    title in games.json can't be re-searched, so they're skipped."""
    title_by_aid = {aid: title for aid, title in games}
    windows = {
        "partial": RESCRAPE_PARTIAL_DAYS * DAY,
        "blank": RESCRAPE_BLANK_DAYS * DAY,
        "full": RESCRAPE_FULL_DAYS * DAY,
    }
    buckets = {"partial": [], "blank": [], "full": []}
    for aid, entry in hltb.items():
        title = title_by_aid.get(aid)
        if not title:
            continue                      # no Steam title to search with -> can't re-scrape
        bucket = rescrape_bucket(entry)
        fetched_at = entry.get("fetched_at") or 0
        if now - fetched_at <= windows[bucket]:
            continue                      # refetched recently -> not yet stale enough
        buckets[bucket].append((fetched_at, aid, title))
    queue = []
    for bucket in ("partial", "blank", "full"):   # priority order
        buckets[bucket].sort(key=lambda t: t[0])  # oldest fetched_at first
        queue.extend((aid, title, bucket) for _ts, aid, title in buckets[bucket])
    return queue


def load_games():
    if not GAMES_FILE.exists():
        return []
    try:
        d = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if d.get("sample"):
        return []
    return [(int(g["appid"]), g.get("title", "")) for g in d.get("games", [])]


def load_hltb():
    if HLTB_FILE.exists():
        try:
            d = json.loads(HLTB_FILE.read_text(encoding="utf-8"))
            return {int(k): v for k, v in (d.get("hltb") or {}).items()}
        except (ValueError, TypeError):
            pass
    return {}


def save_hltb(hltb):
    HLTB_FILE.write_text(json.dumps(
        {"generated_at": int(time.time()), "count": len(hltb),
         "hltb": {str(k): v for k, v in hltb.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")


def git_checkpoint(msg):
    if not IN_ACTIONS:
        return
    try:
        subprocess.run(["git", "add", "hltb.json"], check=False)
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


def main():
    if HowLongToBeat is None:
        log("howlongtobeatpy not installed; nothing to do.")
        return 1
    start = time.time()
    games = load_games()
    if not games:
        log("No games in games.json (or only sample data). Nothing to do.")
        return 0

    hltb = load_hltb()
    # First-pass work: games we've never touched (no entry yet). This always takes
    # priority over re-scraping — finish covering the catalog before revisiting.
    todo = [(aid, title) for aid, title in games if aid not in hltb]
    log(f"Games total {len(games)} | HLTB entries {len(hltb)} | new to resolve {len(todo)}")

    budget = RUN_MINUTES * 60
    last_commit = time.time()
    n_hit = n_blank = 0
    rescraped = newly_filled = 0

    # Live ratios for filling missing/zero HLTB values, computed ONCE from the
    # current corpus's real `raw` triples (estimates can't pollute it — see
    # hltb_estimate.compute_ratios). Fixed at run start for determinism; new real
    # triples found this run feed next run's ratio. Falls back to frozen medians
    # until enough real triples exist.
    ratios, n_triples = HE.compute_ratios(hltb)
    log(f"Fill ratios from {n_triples} real triples "
        f"({'live median' if n_triples >= HE.MIN_TRIPLES_FOR_LIVE else 'frozen fallback'}): "
        f"1 : {ratios['extra_per_main']:.2f} : {ratios['complete_per_main']:.2f}")

    def time_left():
        return budget - (time.time() - start)

    def maybe_checkpoint(msg):
        nonlocal last_commit
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_hltb(hltb)
            git_checkpoint(msg)
            last_commit = time.time()

    # --- Pass 1: resolve never-seen games (priority) ---------------------------- #
    for i, (aid, title) in enumerate(todo, 1):
        if time_left() < TIME_BUFFER:
            log("Time budget reached during first pass; wrapping up.")
            break
        res = hltb_for(title)
        time.sleep(HLTB_DELAY)
        if res is None:
            continue                      # transient error -> leave unresolved, retry next run
        # Build the stored entry: normalizes zeros to null in `raw`, fills missing
        # values from ratios, computes avg over the completed triple, marks `est`,
        # stamps fetched_at. A genuine no-match yields a fully-blank entry.
        hltb[aid] = HE.make_entry(res.get("main"), res.get("extra"),
                                  res.get("complete"), res.get("match"),
                                  time.time(), ratios)
        if hltb[aid].get("avg") is not None:
            n_hit += 1
        else:
            n_blank += 1
        if i % 25 == 0 or i == len(todo):
            log(f"  [new {i}/{len(todo)}] {n_hit} matched, {n_blank} no-match (last: {title[:32]})")
        maybe_checkpoint(f"hltb: {len(hltb)} entries, {n_hit} matched this run (checkpoint)")

    first_pass_done = (time_left() >= TIME_BUFFER)

    # --- Pass 2: re-scrape existing entries with leftover budget (T5) ----------- #
    # Only once the first pass is fully done — otherwise covering new games always wins.
    # Re-fetch is IDENTICAL to a first fetch (hltb_for -> make_entry), so the raw/overwrite
    # model handles merging: real values overwrite raw, estimates recompute, and a transient
    # error (None) leaves the existing entry untouched — we never overwrite good data with a
    # blank. Each refetch restamps fetched_at, so an entry won't be revisited until it's
    # stale again.
    if first_pass_done:
        queue = build_rescrape_queue(games, hltb, int(time.time()))
        if queue:
            n_part = sum(1 for _a, _t, b in queue if b == "partial")
            n_bl = sum(1 for _a, _t, b in queue if b == "blank")
            n_fu = sum(1 for _a, _t, b in queue if b == "full")
            log(f"First pass complete. Re-scrape queue: {len(queue)} stale "
                f"({n_part} partial, {n_bl} blank, {n_fu} full); oldest-first within each.")
            for j, (aid, title, bucket) in enumerate(queue, 1):
                if time_left() < TIME_BUFFER:
                    log("Time budget reached during re-scrape; wrapping up.")
                    break
                res = hltb_for(title)
                time.sleep(HLTB_DELAY)
                if res is None:
                    continue              # transient error -> keep existing entry as-is
                before_real = sum(1 for x in HE.raw_of(hltb[aid]) if HE.is_real(x))
                hltb[aid] = HE.make_entry(res.get("main"), res.get("extra"),
                                          res.get("complete"), res.get("match"),
                                          time.time(), ratios)
                after_real = sum(1 for x in HE.raw_of(hltb[aid]) if HE.is_real(x))
                rescraped += 1
                if after_real > before_real:
                    newly_filled += 1
                if j % 25 == 0 or j == len(queue):
                    log(f"  [rescrape {j}/{len(queue)}] {rescraped} refetched, "
                        f"{newly_filled} gained data (last: {title[:32]})")
                maybe_checkpoint(f"hltb: rescraped {rescraped} ({newly_filled} newly filled), "
                                 f"checkpoint")
        else:
            log("First pass complete. No entries are stale enough to re-scrape yet.")
    elif not todo:
        # Nothing new AND no budget left after building — shouldn't normally happen, but
        # keep the file written.
        log("No new games this run.")

    save_hltb(hltb)
    summary = f"hltb: {len(hltb)} entries"
    if n_hit or n_blank:
        summary += f", {n_hit} newly matched"
    if rescraped:
        summary += f", rescraped {rescraped} ({newly_filled} newly filled)"
    git_checkpoint(summary)
    log(f"\nDone. New: {n_hit} matched, {n_blank} no-match. "
        f"Re-scrape: {rescraped} refetched, {newly_filled} gained data. "
        f"hltb.json now has {len(hltb)} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

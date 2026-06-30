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

Why a separate cadence works perfectly here: HLTB completion times are STATIC — a game's
"how long to beat" doesn't change. So each game needs exactly ONE successful HLTB lookup,
ever. This job fills hltb.json for games that don't have an entry yet and never re-fetches
a game it already resolved. It can run slowly in the background without holding anything up.

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
    # Only games we've never successfully resolved (no entry yet). Already-resolved games
    # — including ones recorded as a definite blank (no match) — are skipped forever.
    todo = [(aid, title) for aid, title in games if aid not in hltb]
    log(f"Games total {len(games)} | HLTB resolved {len(hltb)} | to resolve {len(todo)}")
    if not todo:
        log("Every game already has an HLTB entry. Done.")
        save_hltb(hltb)
        return 0

    budget = RUN_MINUTES * 60
    last_commit = time.time()
    n_hit = n_blank = 0

    # Live ratios for filling missing/zero HLTB values, computed ONCE from the
    # current corpus's real `raw` triples (estimates can't pollute it — see
    # hltb_estimate.compute_ratios). Fixed at run start for determinism; new real
    # triples found this run feed next run's ratio. Falls back to frozen medians
    # until enough real triples exist.
    ratios, n_triples = HE.compute_ratios(hltb)
    log(f"Fill ratios from {n_triples} real triples "
        f"({'live median' if n_triples >= HE.MIN_TRIPLES_FOR_LIVE else 'frozen fallback'}): "
        f"1 : {ratios['extra_per_main']:.2f} : {ratios['complete_per_main']:.2f}")

    for i, (aid, title) in enumerate(todo, 1):
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached; wrapping up.")
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
            log(f"  [{i}/{len(todo)}] {n_hit} matched, {n_blank} no-match (last: {title[:32]})")
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_hltb(hltb)
            git_checkpoint(f"hltb: {len(hltb)} games resolved (checkpoint)")
            last_commit = time.time()

    save_hltb(hltb)
    git_checkpoint(f"hltb: {len(hltb)} games resolved")
    log(f"\nDone. This run: {n_hit} matched, {n_blank} no-match. hltb.json now has "
        f"{len(hltb)} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

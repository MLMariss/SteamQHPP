#!/usr/bin/env python3
"""
Steam QHPP — recent-review refresher
====================================
A SEPARATE, independent job from scraper.py. It keeps each game's *recent*
(last-28-day) Steam review score fresh, so the frontend can show a recent-vs-all-time
trend (improving / stable / declining).

Why it's its own script + its own file:
  * scraper.py owns games.json (catalog, price, all-time rating, tags, last_update_ts).
  * THIS writes a separate recent.json keyed by appid -> {recent_pct, recent_count,
    recent_scraped_at}. Two Actions writing the same file would collide on push; two
    Actions writing *different* files never do (a git pull --rebase before push always
    applies cleanly).

The recent score is a 28-day rolling window, so it drifts daily even with no new
reviews. We can't keep all ~90k games perfectly fresh within the storefront rate
limit, so we spend calls where reviews are actually likely to be moving:

  * Cooldown (RECENT_COOLDOWN_DAYS): never re-check a score younger than this — a day
    of new reviews barely moves a 28-day window, so re-checking is wasted budget.
  * Update-priority: recently *updated* games (from last_update_ts in games.json) jump
    the queue — a patch is exactly when reviews swing. Games with no/old updates get a
    much longer cooldown (checked rarely, never skipped forever).
  * Low-volume de-prioritised: a game with < RECENT_MIN_COUNT recent reviews is noisy,
    so it sinks in the queue (still eligible, just last in line).
  * Oldest-first tiebreak so everything eventually refreshes.

The recent window uses appreviews with filter=all&day_range=28: query_summary then
reflects the windowed reviews. (~30 days is what Steam's "Recent Reviews" approximates.)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"          # read-only here (owned by scraper.py)
RECENT_FILE = HERE / "recent.json"        # THIS file's output (committed)

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()   # not required (appreviews is keyless)
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "180"))
CHECKPOINT_SECONDS = 600
TIME_BUFFER = 90

RECENT_WINDOW_DAYS = 28          # the "recent" window (Steam shows ~30d)
RECENT_COOLDOWN_DAYS = 4         # don't re-check a recent score younger than this
NOUPDATE_COOLDOWN_DAYS = 30      # games with no/old updates: check far less often
UPDATE_ACTIVE_DAYS = 90          # "recently updated" = patched within this many days
RECENT_MIN_COUNT = 50            # below this many recent reviews -> de-prioritise (noisy)

STEAM_DELAY = 1.5                # storefront limit (~200/5min) — shared with scraper if co-running
MAX_RETRIES = 4

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
HEADERS = {"User-Agent": "Mozilla/5.0 (steam-qhpp recent-refresher; github pages dataset builder)",
           "Accept-Language": "en-US,en;q=0.9"}
COOKIES = {"birthtime": "568022401", "mature_content": "1",
           "Steam_Language": "english", "wants_mature_content": "1"}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.cookies.update(COOKIES)


def log(msg):
    print(msg, flush=True)


def get(url, *, params=None, timeout=30):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = min(90, 5 * attempt)
                log(f"  429 rate-limited, sleeping {wait}s"); time.sleep(wait); continue
            if r.status_code == 403:
                log("  403 (soft-limit); cooling down 5 min"); time.sleep(300); continue
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
# Recent score for one game (28-day window)
# --------------------------------------------------------------------------- #
def recent_score(appid):
    """Return (recent_pct, recent_count) for ~the last RECENT_WINDOW_DAYS, or (None, 0).
    day_range only takes effect with filter=all; query_summary is then windowed."""
    data = get(f"https://store.steampowered.com/appreviews/{appid}",
               params={"json": 1, "filter": "all", "language": "all",
                       "purchase_type": "all", "day_range": RECENT_WINDOW_DAYS,
                       "num_per_page": 0})
    if not isinstance(data, dict) or data.get("success") != 1:
        return None, 0
    s = data.get("query_summary", {})
    pos, neg = int(s.get("total_positive", 0)), int(s.get("total_negative", 0))
    if pos + neg == 0:
        return None, 0
    return round(pos / (pos + neg) * 100), pos + neg


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def load_games():
    if not GAMES_FILE.exists():
        return []
    try:
        d = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if d.get("sample"):
        return []
    return d.get("games", [])


def load_recent():
    if RECENT_FILE.exists():
        try:
            d = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
            return d.get("recent", {})
        except ValueError:
            pass
    return {}


def save_recent(recent):
    RECENT_FILE.write_text(json.dumps(
        {"generated_at": int(time.time()), "window_days": RECENT_WINDOW_DAYS,
         "count": len(recent), "recent": recent},
        ensure_ascii=False, indent=2), encoding="utf-8")


def git_checkpoint(msg):
    """Commit recent.json only; rebase first so it never fights the main scraper's
    games.json pushes (different files => always a clean replay)."""
    if not IN_ACTIONS:
        return
    try:
        subprocess.run(["git", "add", "recent.json"], check=False)
        if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode != 0:
            subprocess.run(["git", "commit", "-m", msg], check=False)
            subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False)
            subprocess.run(["git", "push"], check=False)
            log(f"  committed: {msg}")
    except Exception as e:
        log(f"  git checkpoint failed: {e}")


# --------------------------------------------------------------------------- #
# Eligibility + priority
# --------------------------------------------------------------------------- #
def is_eligible(rec, last_update_ts, now):
    """Past its cooldown? Actively-updated games use the short cooldown; dormant/
    no-update games use the long one (so they're checked rarely, not never)."""
    age = now - rec.get("recent_scraped_at", 0)
    actively_updated = last_update_ts and (now - last_update_ts) <= UPDATE_ACTIVE_DAYS * 86400
    cooldown = RECENT_COOLDOWN_DAYS if actively_updated else NOUPDATE_COOLDOWN_DAYS
    return age >= cooldown * 86400


def priority(rec, last_update_ts, all_time_count, now):
    """Higher = refresh sooner. Never-fetched first, recent updates boosted, low recent
    volume penalised, staleness as a capped tiebreak."""
    score = 0.0
    sat = rec.get("recent_scraped_at", 0)
    if sat == 0:
        score += 1000                                   # never fetched -> do first
    if last_update_ts:
        days = (now - last_update_ts) / 86400
        score += 300 if days <= 30 else 150 if days <= 90 else 50 if days <= 365 else 0
    rcount = rec.get("recent_count")
    if rcount is None:
        rcount = all_time_count                          # unknown -> use all-time as a proxy
    if rcount is not None and rcount < RECENT_MIN_COUNT:
        score -= 200                                     # noisy/low-volume -> de-prioritise
    score += min(200, (now - sat) / 86400)               # older = higher, capped
    return score


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    start = time.time()
    games = load_games()
    if not games:
        log("No real games.json yet (run scraper.py first); nothing to refresh.")
        return 0
    recent = load_recent()
    now = int(time.time())

    # candidates = eligible games, sorted by priority desc
    cands = []
    for g in games:
        aid = str(g["appid"])
        rec = recent.get(aid, {})
        lu = g.get("last_update_ts")
        if is_eligible(rec, lu, now):
            cands.append((priority(rec, lu, g.get("review_count"), now), int(aid), lu))
    cands.sort(reverse=True)

    log(f"Catalog {len(games)} | recent.json has {len(recent)} | eligible now: {len(cands)}")
    log(f"Budget: {RUN_MINUTES} min · window {RECENT_WINDOW_DAYS}d · cooldown "
        f"{RECENT_COOLDOWN_DAYS}d (dormant {NOUPDATE_COOLDOWN_DAYS}d)")

    budget = RUN_MINUTES * 60
    last_commit = time.time()
    done = 0
    for _score, aid, _lu in cands:
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached; wrapping up.")
            break
        pct, count = recent_score(aid)
        time.sleep(STEAM_DELAY)
        if pct is not None:
            recent[str(aid)] = {"recent_pct": pct, "recent_count": count,
                                "recent_scraped_at": int(time.time())}
            done += 1
            log(f"  recent {aid:>8}: {pct}% ({count} in {RECENT_WINDOW_DAYS}d)")
        else:
            # no recent reviews -> still stamp it so the cooldown applies (don't re-hammer)
            recent[str(aid)] = {"recent_pct": None, "recent_count": 0,
                                "recent_scraped_at": int(time.time())}
            log(f"  recent {aid:>8}: no reviews in window")

        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_recent(recent)
            git_checkpoint(f"recent: refreshed {done} this run ({len(recent)} tracked)")
            last_commit = time.time()

    save_recent(recent)
    git_checkpoint(f"recent: refreshed {done} ({len(recent)} tracked)")
    log(f"\nDone. Refreshed {done} recent scores. {len(recent)} games tracked total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Steam QHPP — playtime refresher (sentiment-split "hours on record")
===================================================================
A SEPARATE, independent job from scraper.py. It captures, per game, how long
reviewers have actually played it — split by whether they recommended it — from
the public `appreviews` endpoint. This is the number Steam shows on each review
card ("X hrs on record"), aggregated into medians.

Why it's its own script + its own file (the one-writer-per-file rule):
  * scraper.py owns games.json; recent_refresh.py owns recent.json; etc.
  * THIS writes a separate playtime.json keyed by appid. Two Actions writing the
    same file collide on push; two writing *different* files never do (a git pull
    --rebase before push always replays cleanly). See ARCHITECTURE.md §3/§4.

What it stores per game (see save_playtime for the exact shape):
  * median playtime (minutes) for reviewers who RECOMMENDED   (voted_up = true)
  * median playtime (minutes) for reviewers who did NOT       (voted_up = false)
  * a combined median across the whole sample
  * the sample size behind each median (so the frontend can flag thin data)
  * a resumable pagination cursor + how many reviews we've walked so far, so a
    LATER run can pick up where this one stopped and deepen the sample without
    re-scraping (200 now -> 500 -> full, per game, on demand).

Why median, not mean:
  Steam playtime is heavily distorted at the top end — idle/AFK inflation, the
  "pause button" problem, MMO/farming grinders, and long-tail 1000h outliers.
  All of those attack the mean. The median is robust to every one of them. We
  also keep sample sizes so a "3 detractors" median can be shown as low-confidence.

Why split by sentiment:
  Empirically the two segments can differ enough to flip a game's story — players
  who enjoy a game log far more hours, while players hit by (e.g.) performance
  problems bail early. Surfacing "fans play 80h, detractors quit at 3h" is a
  value signal no single number captures. (For some games the gap is small; that
  variance is itself informative, which is why we store both segments raw.)

RATE-LIMIT ISOLATION — IMPORTANT:
  This hits store.steampowered.com, which shares a ~200-request / 5-minute / IP
  budget with scraper.py, price_and_sale.py, and recent_refresh.py. To avoid
  starving those jobs (a 403 soft-limit here costs a 5-MINUTE cooldown, same as
  them), this job is scheduled in its OWN cron slot, staggered away from the other
  storefront jobs so it runs with the budget to itself. Its STEAM_DELAY is a touch
  more conservative than the others for the same reason. Do NOT co-schedule it with
  the other storefront jobs without re-tuning all their delays together.

  Cost: 200 reviews/game at 100/page = 2 requests/game, so ~1 game / (2*DELAY).
  At DELAY=2.0s that's ~900 games/hour when it runs alone.
"""

import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"            # read-only here (owned by scraper.py)
PLAYTIME_FILE = HERE / "playtime.json"      # THIS file's output (committed)

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()  # not required (appreviews is keyless)
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "180"))
CHECKPOINT_SECONDS = 600
TIME_BUFFER = 90

# --- sampling depth -------------------------------------------------------- #
# TARGET_REVIEWS is how many reviews we try to walk per game on a normal pass.
# Start at 200 (2 pages). To DEEPEN later, either bump this and let games become
# eligible again, or set DEEPEN_TARGET as an env override for a one-off deep run
# (it resumes from each game's saved cursor — see resume logic in scrape_game).
TARGET_REVIEWS = int(os.environ.get("TARGET_REVIEWS", "200"))
PER_PAGE = 100                   # appreviews hard max is 100/page
# Optional deep-run override: `DEEPEN_TARGET=500 python playtime_refresh.py`
# raises the target for THIS run only and prefers games that haven't hit it yet.
DEEPEN_TARGET = int(os.environ.get("DEEPEN_TARGET", "0"))

MIN_AGE_DAYS = 0                 # playtime is meaningful from day one (no suppression)
COOLDOWN_DAYS = 14               # don't re-walk a game's reviews younger than this
NOUPDATE_COOLDOWN_DAYS = 45      # dormant games: refresh far less often
UPDATE_ACTIVE_DAYS = 90          # "recently updated" = patched within this many days
MIN_SEGMENT_FOR_MEDIAN = 3       # below this many samples, a segment median is null
                                  # (kept, but marked low-confidence via the count)

STEAM_DELAY = 2.0                # storefront limit (~200/5min); a touch slower than the
                                  # other storefront jobs since this one paginates.
MAX_RETRIES = 4

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
HEADERS = {"User-Agent": "Mozilla/5.0 (steam-qhpp playtime-refresher; github pages dataset builder)",
           "Accept-Language": "en-US,en;q=0.9"}
COOKIES = {"birthtime": "568022401", "mature_content": "1",
           "Steam_Language": "english", "wants_mature_content": "1"}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.cookies.update(COOKIES)


def log(msg):
    print(msg, flush=True)


def get(url, *, params=None, timeout=30):
    """Same retry/backoff contract as the other storefront scrapers: 429 -> short
    sleep, 403 soft-limit -> 5-min cooldown, transient errors -> capped backoff."""
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
# Playtime for one game — walk appreviews, split by sentiment
# --------------------------------------------------------------------------- #
# We page through the public appreviews endpoint (filter=recent so pagination is
# stable and cursor-driven), pulling author.playtime_forever for each review and
# bucketing by voted_up. We accumulate onto any playtime we already gathered in a
# previous run (resume via the saved cursor), so deepening never re-scrapes.
#
# Field note: playtime_forever is total lifetime minutes in that game (what we
# want). We deliberately ignore playtime_at_review — total time is the metric of
# interest here. Some author objects omit playtime fields entirely (rare); those
# reviews are simply skipped for the median but still counted as walked.
def _extract_playtime(review):
    """Return author.playtime_forever in minutes, or None if not present/valid."""
    a = review.get("author") or {}
    pt = a.get("playtime_forever")
    try:
        pt = int(pt)
    except (TypeError, ValueError):
        return None
    return pt if pt > 0 else None


def scrape_game(appid, prior, target):
    """Walk up to `target` total reviews for one game, resuming from prior state.

    `prior` is this game's existing playtime.json record (may be {}). We resume
    from prior['cursor'] and add to prior's stored raw sample lists so a deeper
    run extends the sample instead of restarting.

    Returns an updated record dict, or None on hard failure (leave prior intact).
    """
    # Resume state: raw per-segment minute lists + how many reviews we've walked.
    raw = (prior.get("raw") or {})
    up_list = list(raw.get("up") or [])       # minutes for voted_up=true reviewers
    down_list = list(raw.get("down") or [])   # minutes for voted_up=false reviewers
    walked = int(prior.get("walked") or 0)
    cursor = prior.get("cursor") or "*"

    # Already at/over target, or Steam has no more reviews? Nothing to gather.
    if (walked >= target or prior.get("exhausted")) and prior:
        return None

    added = 0
    pages = 0
    exhausted = False
    max_pages = (target // PER_PAGE) + 2      # safety bound on the loop
    while walked < target and pages < max_pages:
        data = get(f"https://store.steampowered.com/appreviews/{appid}",
                   params={"json": 1, "language": "all", "purchase_type": "all",
                           "num_per_page": PER_PAGE, "filter": "recent",
                           "cursor": cursor})
        time.sleep(STEAM_DELAY)
        if not isinstance(data, dict) or data.get("success") != 1:
            break
        reviews = data.get("reviews") or []
        if not reviews:
            exhausted = True                   # no more reviews exist for this game
            break
        for rv in reviews:
            walked += 1
            pt = _extract_playtime(rv)
            if pt is None:
                continue
            if rv.get("voted_up"):
                up_list.append(pt)
            else:
                down_list.append(pt)
            added += 1

        next_cursor = data.get("cursor")
        pages += 1
        # Steam returns the SAME cursor at the end; stop if it doesn't advance.
        if not next_cursor or next_cursor == cursor:
            cursor = next_cursor or cursor
            exhausted = True
            break
        cursor = next_cursor
        if len(reviews) < PER_PAGE:
            exhausted = True                   # last (partial) page -> no more
            break

    return _build_record(up_list, down_list, walked, cursor, added, exhausted)


def _median_or_none(values):
    """Median (rounded to int minutes) when the segment has enough samples, else
    None. We keep the raw list regardless so a later run can recompute/deepen."""
    if len(values) < MIN_SEGMENT_FOR_MEDIAN:
        return None
    return int(round(statistics.median(values)))


def _build_record(up_list, down_list, walked, cursor, added, exhausted=False):
    combined = up_list + down_list
    return {
        # Headline medians (minutes). Null when the segment is too thin to trust.
        "median_up": _median_or_none(up_list),
        "median_down": _median_or_none(down_list),
        "median_all": _median_or_none(combined),
        # Sample sizes behind each median (frontend uses these for a confidence hint).
        "n_up": len(up_list),
        "n_down": len(down_list),
        "n_all": len(combined),
        # Resume state for deepening later without re-scraping.
        "walked": walked,            # total reviews paged through so far
        "cursor": cursor,            # pass back as ?cursor= to continue
        "exhausted": exhausted,      # True = Steam has no more reviews (don't retry for depth)
        "scraped_at": int(time.time()),
        # Option-B style raw storage: keep the underlying samples so a future run
        # can extend them and recompute medians at any depth. This mirrors the
        # HLTB `raw` sub-object pattern (ARCHITECTURE.md). Kept compact (ints).
        "raw": {"up": up_list, "down": down_list},
        "_last_added": added,        # diagnostics only (how many this run added)
    }


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


def load_playtime():
    if PLAYTIME_FILE.exists():
        try:
            d = json.loads(PLAYTIME_FILE.read_text(encoding="utf-8"))
            return d.get("playtime", {})
        except ValueError:
            pass
    return {}


def save_playtime(playtime):
    PLAYTIME_FILE.write_text(json.dumps(
        {"generated_at": int(time.time()), "target_reviews": TARGET_REVIEWS,
         "count": len(playtime), "playtime": playtime},
        ensure_ascii=False, indent=2), encoding="utf-8")


def git_checkpoint(msg):
    """Commit playtime.json only; rebase first so it never fights other jobs'
    pushes (different files => always a clean replay). Mirrors recent_refresh.py."""
    if not IN_ACTIONS:
        return
    try:
        subprocess.run(["git", "add", "playtime.json"], check=False)
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
# Eligibility + priority
# --------------------------------------------------------------------------- #
def effective_target():
    """Normal runs use TARGET_REVIEWS. A deep run (DEEPEN_TARGET set) raises it."""
    return max(TARGET_REVIEWS, DEEPEN_TARGET) if DEEPEN_TARGET else TARGET_REVIEWS


def is_eligible(rec, last_update_ts, now, target):
    """Eligible if: never scraped; OR still short of target AND more reviews remain
    to fetch (not exhausted); OR past its cooldown. Actively-updated games use the
    short cooldown, dormant ones the long one."""
    if not rec:
        return True
    walked = int(rec.get("walked") or 0)
    exhausted = bool(rec.get("exhausted"))      # Steam ran out of reviews before target
    if walked < target and not exhausted:
        return True                             # more depth available -> resume
    age = now - rec.get("scraped_at", 0)
    actively_updated = last_update_ts and (now - last_update_ts) <= UPDATE_ACTIVE_DAYS * 86400
    cooldown = COOLDOWN_DAYS if actively_updated else NOUPDATE_COOLDOWN_DAYS
    return age >= cooldown * 86400


def priority(rec, last_update_ts, all_time_count, now, target):
    """Higher = do sooner. Never-scraped first, then games still short of target,
    then recent updates, then staleness. Low all-time review counts sink."""
    score = 0.0
    if not rec:
        score += 1000                            # never scraped -> do first
    elif int(rec.get("walked") or 0) < target:
        score += 500                             # partially scraped -> finish it
    if last_update_ts:
        days = (now - last_update_ts) / 86400
        score += 300 if days <= 30 else 150 if days <= 90 else 50 if days <= 365 else 0
    if all_time_count is not None and all_time_count < 10:
        score -= 300                             # almost no reviews -> useless median
    score += min(200, (now - rec.get("scraped_at", 0)) / 86400) if rec else 0
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
    playtime = load_playtime()
    now = int(time.time())
    target = effective_target()

    cands = []
    for g in games:
        aid = str(g["appid"])
        rec = playtime.get(aid, {})
        lu = g.get("last_update_ts")
        if is_eligible(rec, lu, now, target):
            cands.append((priority(rec, lu, g.get("review_count"), now, target),
                          int(aid), lu))
    cands.sort(reverse=True)

    mode = f"DEEPEN to {target}" if DEEPEN_TARGET else f"target {target}"
    log(f"Catalog {len(games)} | playtime.json has {len(playtime)} | eligible now: {len(cands)}")
    log(f"Budget: {RUN_MINUTES} min · {mode} reviews/game · delay {STEAM_DELAY}s · cooldown "
        f"{COOLDOWN_DAYS}d (dormant {NOUPDATE_COOLDOWN_DAYS}d)")

    budget = RUN_MINUTES * 60
    last_commit = time.time()
    done = 0
    for _score, aid, _lu in cands:
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached; wrapping up.")
            break
        prior = playtime.get(str(aid), {})
        rec = scrape_game(aid, prior, target)
        if rec is not None:
            playtime[str(aid)] = rec
            done += 1
            mu = rec["median_up"]; md = rec["median_down"]
            mu_h = f"{mu/60:.1f}h" if mu is not None else "—"
            md_h = f"{md/60:.1f}h" if md is not None else "—"
            log(f"  playtime {aid:>8}: fans {mu_h} (n={rec['n_up']}) · "
                f"detractors {md_h} (n={rec['n_down']}) · walked {rec['walked']}")

        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_playtime(playtime)
            git_checkpoint(f"playtime: updated {done} this run ({len(playtime)} tracked)")
            last_commit = time.time()

    save_playtime(playtime)
    git_checkpoint(f"playtime: updated {done} ({len(playtime)} tracked)")
    log(f"\nDone. Updated {done} games. {len(playtime)} tracked total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

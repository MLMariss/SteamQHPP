#!/usr/bin/env python3
"""
One-off (idempotent) backfill for the missing `last_update_ts` field in games.json.

Every game currently in games.json was scraped before scraper.py started writing
last_update_ts, so the field is absent and the frontend shows "no updates" for all of
them. This script fills it in WITHOUT a full re-scrape: it only touches games that are
missing the field, and uses Steam's News API (api.steampowered.com), which has a large
rate budget separate from the tight storefront limit -- so backfilling the whole
catalog is cheap (~NEWS_DELAY per game).

The update-detection logic here is copied verbatim from scraper.py's
last_update_from_news / _is_update_item so backfilled values match what future scrapes
produce. Run again any time; games that already have the field are skipped.

Usage:
    python3 backfill_updates.py            # backfill, write games.json
    python3 backfill_updates.py --dry-run  # report only, no write
    python3 backfill_updates.py --all      # recompute for ALL games (not just missing)
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"

DRY = "--dry-run" in sys.argv
RECOMPUTE_ALL = "--all" in sys.argv

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()   # optional
NEWS_DELAY = 0.3
MAX_RETRIES = 4
SAVE_EVERY = 200          # write progress to disk every N games (crash-safety)

HEADERS = {"User-Agent": "Mozilla/5.0 (steam-qhpp update backfill; github pages dataset builder)",
           "Accept-Language": "en-US,en;q=0.9"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# --- update-detection: copied from scraper.py so results are identical ------- #
_UPDATE_TAGS = {"patchnotes"}
_UPDATE_WORDS = ("update", "patch", "hotfix", "changelog", "release notes",
                 "version", "build ", "bug fix", "bugfix", "fixes", "balance")
_NOT_UPDATE = ("sale", "discount", "% off", "wishlist", "now available", "out now",
               "launch", "release date", "pre-order", "preorder", "trailer", "soundtrack")


def _is_update_item(item):
    if any(t in _UPDATE_TAGS for t in (item.get("tags") or [])):
        return True
    text = (str(item.get("title", "")) + " " + str(item.get("feedlabel", ""))).lower()
    if any(bad in text for bad in _NOT_UPDATE):
        return False
    return any(w in text for w in _UPDATE_WORDS)


def get(url, *, params=None, timeout=30):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = min(90, 5 * attempt)
                print(f"  429 rate-limited, sleeping {wait}s", flush=True)
                time.sleep(wait); continue
            r.raise_for_status()
            try:
                return r.json()
            except ValueError:
                return None
        except requests.RequestException as e:
            wait = min(30, 3 * attempt)
            print(f"  request error ({attempt}/{MAX_RETRIES}): {e}; retry in {wait}s", flush=True)
            time.sleep(wait)
    return None


def last_update_from_news(appid):
    params = {"appid": appid, "count": 20, "maxlength": 1, "format": "json"}
    if STEAM_API_KEY:
        params["key"] = STEAM_API_KEY
    data = get("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/", params=params)
    time.sleep(NEWS_DELAY)
    if not isinstance(data, dict):
        return None
    items = (data.get("appnews") or {}).get("newsitems") or []
    stamps = [it.get("date") for it in items if _is_update_item(it) and it.get("date")]
    return max(stamps) if stamps else None


def save(data):
    data["generated_at"] = int(time.time())
    GAMES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if not GAMES_FILE.exists():
        print("games.json not found.")
        return 1
    data = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    games = data.get("games", [])

    if RECOMPUTE_ALL:
        todo = list(games)
    else:
        todo = [g for g in games if "last_update_ts" not in g]

    print(f"games.json: {len(games)} games | to backfill: {len(todo)}"
          f"{' (recompute ALL)' if RECOMPUTE_ALL else ' (missing field only)'}")
    if DRY:
        est = len(todo) * NEWS_DELAY / 60
        print(f"[dry-run] would query {len(todo)} games (~{est:.1f} min). No write.")
        return 0
    if not todo:
        print("Nothing to backfill; every game already has last_update_ts.")
        return 0

    found = missing = 0
    for i, g in enumerate(todo, 1):
        aid = g["appid"]
        ts = last_update_from_news(aid)
        g["last_update_ts"] = ts          # may be None -> explicit "no updates found"
        if ts:
            found += 1
        else:
            missing += 1
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {found} with updates, {missing} without "
                  f"(last: {g['title'][:30]})", flush=True)
        if i % SAVE_EVERY == 0:
            save(data)
            print(f"  ...progress saved ({i} done)", flush=True)

    save(data)
    print(f"\nDone. Backfilled {len(todo)} games: {found} have an update date, "
          f"{missing} have no update posts (genuinely or filtered).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

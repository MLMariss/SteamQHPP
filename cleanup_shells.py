#!/usr/bin/env python3
"""
One-off (idempotent) cleanup for Steam QHPP.

Removes "empty shell" entries from games.json — games that were scraped while still
unreleased (coming-soon / TBA / vague future date), so they carry no real data:
no price, no rating, and no HLTB, and no concrete past release date (release_ts is
None or in the future).

These shells are NOT deleted-and-forgotten: each is filed into catalog["pending"] =
{appid: release_ts|null} so the main scraper's waiting room promotes it to a real
scrape once its release date arrives. (Per design: unreleased games are remembered,
never permanently skipped.)

Free games and released-but-thin games (e.g. a real game with reviews but no HLTB
match) are KEPT — they have a release_ts and/or is_free, so they don't match the
shell test.

Safe to run repeatedly: on a clean dataset it removes 0 and changes nothing.

Usage:
    python3 cleanup_shells.py            # apply changes, write files
    python3 cleanup_shells.py --dry-run  # report only, write nothing
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"
CATALOG_FILE = HERE / "catalog.json"

DRY = "--dry-run" in sys.argv


def is_shell(g, now):
    """A shell = no usable data AND not actually released."""
    has_price = g.get("price_final") is not None or g.get("price_initial") is not None
    has_rating = g.get("rating_pct") is not None
    has_hltb = g.get("hltb_avg") is not None
    if g.get("is_free"):
        return False                       # free games legitimately have null price
    if has_price or has_rating or has_hltb:
        return False                       # any real signal => keep
    ts = g.get("release_ts")
    # Dataless AND (never got a concrete release date OR not out yet) => shell.
    return ts is None or ts > now


def main():
    if not GAMES_FILE.exists():
        print("games.json not found; nothing to do.")
        return 0
    now = int(time.time())

    data = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    games = data.get("games", [])
    keep, shells = [], []
    for g in games:
        (shells if is_shell(g, now) else keep).append(g)

    print(f"games.json: {len(games)} total -> {len(keep)} kept, {len(shells)} shells removed")
    if shells:
        # Show the release_date breakdown of what we're removing, for sanity.
        from collections import Counter
        c = Counter(g.get("release_date") for g in shells)
        print("  removed by release_date label:")
        for val, n in c.most_common(10):
            print(f"    {n:5}  {val!r}")

    # Load catalog and file shells into the pending waiting room.
    catalog = {}
    if CATALOG_FILE.exists():
        try:
            catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except ValueError:
            catalog = {}
    catalog.setdefault("last_sync", 0)
    catalog.setdefault("skipped", [])
    catalog.setdefault("priority", [])
    pend = catalog.get("pending")
    if isinstance(pend, list):
        pending = {int(a): None for a in pend}
    elif isinstance(pend, dict):
        pending = {int(k): v for k, v in pend.items()}
    else:
        pending = {}

    added = 0
    for g in shells:
        aid = int(g["appid"])
        if aid not in pending:
            added += 1
        # Store its release_ts if we parsed one (future date), else None (TBA). The
        # scraper promotes ts!=None && ts<=now; None waits for a last_modified bump.
        pending[aid] = g.get("release_ts")
    print(f"pending waiting room: {len(pending)} total (+{added} newly filed from shells)")

    if DRY:
        print("\n[dry-run] no files written.")
        return 0

    # Write games.json back, preserving structure + refreshing count/generated_at.
    data["games"] = sorted(keep, key=lambda g: g["appid"])
    data["count"] = len(keep)
    data["generated_at"] = now
    GAMES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    catalog["pending"] = {str(k): v for k, v in pending.items()}
    CATALOG_FILE.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    print("\nWrote games.json and catalog.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

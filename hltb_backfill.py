#!/usr/bin/env python3
"""
SteamQHPP — HLTB one-time backfill
==================================
A ONE-TIME sweep of the existing hltb.json, run once after deploying the new
estimation logic. It does NOT fetch anything from HowLongToBeat — it only
re-processes the data already there.

Why this exists
---------------
Before the estimation upgrade, `avg` was the mean of whatever HLTB values
happened to be present. A game with only a main-story time got avg == main
(understated); a game with only a completionist time got avg == that long number
(overstated). Since QHPP defaults to the avg metric, ~347 games had a skewed
quality score. New games fetched from now on are fixed at the source by
hltb_refresh.py, but the games already in the file need this one pass to:

  1. Add the `raw` ground-truth block (zeros normalized to null).
  2. Fill missing/zero main/extra/complete from the live median ratio, anchored
     on whatever real value exists.
  3. Recompute avg over the completed triple.
  4. Mark estimated fields in `est` (drives the frontend's distinct color).
  5. Stamp `fetched_at` (set to the file's generated_at — our best estimate of
     when these entries were originally fetched — so the FUTURE re-scrape can
     order by staleness honestly). Re-scraping is not done here; this only lays
     the groundwork.

Idempotent: running it twice produces the same result (estimates derive from
`raw`, never from prior estimates), so it's safe to re-run.

Usage:
    python3 hltb_backfill.py            # writes hltb.json in place, prints a report
    python3 hltb_backfill.py --dry-run  # report only, write nothing
"""

import json
import sys
import time
from pathlib import Path

import hltb_estimate as HE

HERE = Path(__file__).resolve().parent
HLTB_FILE = HERE / "hltb.json"


def main():
    dry = "--dry-run" in sys.argv

    if not HLTB_FILE.exists():
        print("hltb.json not found; nothing to do.")
        return 1

    doc = json.loads(HLTB_FILE.read_text(encoding="utf-8"))
    hltb = {int(k): v for k, v in (doc.get("hltb") or {}).items()}
    if not hltb:
        print("hltb.json has no entries; nothing to do.")
        return 0

    # Best estimate of when existing entries were fetched: the file's own stamp.
    default_fetched = int(doc.get("generated_at") or time.time())

    # Ratios from the REAL raw triples in the current data (estimates excluded).
    ratios, n_triples = HE.compute_ratios(hltb)
    mode = "live median" if n_triples >= HE.MIN_TRIPLES_FOR_LIVE else "frozen fallback"
    print(f"Fill ratios from {n_triples} real triples ({mode}):")
    print(f"  main : extra : complete  =  1 : {ratios['extra_per_main']:.4f} "
          f": {ratios['complete_per_main']:.4f}")
    print()

    # Counters for the report
    n_total = len(hltb)
    n_filled = 0            # entries that received >=1 estimated value
    n_avg_changed = 0       # entries whose avg value actually changed
    n_blank = 0             # entries with no usable data (left blank)
    n_full_real = 0         # entries with all 3 real (no estimation needed)
    big_changes = []        # largest avg corrections, for the report

    for aid, entry in hltb.items():
        old_avg = entry.get("avg")

        # Stamp fetched_at if missing (existing entries predate it).
        if "fetched_at" not in entry:
            entry["fetched_at"] = default_fetched

        HE.fill_entry(entry, ratios)     # mutates: adds raw, fills, sets avg + est

        rm, re_, rc = HE.raw_of(entry)
        present = sum(HE.is_real(x) for x in (rm, re_, rc))
        if present == 0:
            n_blank += 1
        elif present == 3 and not entry.get("est"):
            n_full_real += 1

        if entry.get("est"):
            n_filled += 1

        new_avg = entry.get("avg")
        if old_avg != new_avg:
            n_avg_changed += 1
            if old_avg is not None and new_avg is not None:
                big_changes.append((abs(new_avg - old_avg), entry.get("match"),
                                    old_avg, new_avg, entry.get("est")))

    # ---- report ----
    print(f"Entries:                 {n_total}")
    print(f"  full real (3/3):       {n_full_real}")
    print(f"  received estimates:    {n_filled}")
    print(f"  left blank (no data):  {n_blank}")
    print(f"  avg value corrected:   {n_avg_changed}")
    print()
    big_changes.sort(reverse=True)
    if big_changes:
        print("Largest avg corrections:")
        for delta, match, old, new, est in big_changes[:12]:
            print(f"  {str(match)[:34]:34s} {old:>7} -> {new:<7} (Δ{new-old:+.1f})  est={est}")
        print()

    if dry:
        print("--dry-run: no file written.")
        return 0

    doc["hltb"] = {str(k): v for k, v in hltb.items()}
    doc["count"] = len(hltb)
    doc["generated_at"] = int(time.time())
    HLTB_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"Wrote {HLTB_FILE.name} ({len(hltb)} entries).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

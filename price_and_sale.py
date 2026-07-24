#!/usr/bin/env python3
"""
Steam QHPP — prices + sale end-dates refresher
===========================================================================
One SEPARATE, independent job that owns the whole fast-changing PRICING layer:
current price, discount %, and sale end-date. It writes a single prices.json; the main
scraper no longer touches any of these (they change far more often than catalog/tags do,
and keeping them here keeps the slow scrape lean and avoids write collisions).

Why prices and sales are bundled (vs. two jobs): they're the same logical fact — "what
does this game cost right now" — and they refresh on the same cadence. Bundling means one
schedule, one file, one merge on the frontend. They use two endpoints, but that's an
implementation detail inside this one job.

The two endpoints, both cheap:
  1. PRICES — store.steampowered.com/api/appdetails?filters=price_overview&appids=<CSV>
     This is the ONE appdetails variant Valve still lets you BATCH: pass many comma-
     separated appids and it returns price_overview for all of them in a single call.
     (Full appdetails is one-appid-only since 2015; price-only is the exception.) So the
     entire ~3,200-game catalog refreshes in ~ceil(N/BATCH) calls instead of N.
  2. IStoreBrowseService/GetItems/v1 (batched) — used for two things:
     a. PACKAGE PRICES for the apps step 1 returned no price for (package-only storefronts
        like the shared Call of Duty launcher). See fetch_package_prices.
     b. SALE END DATES, reading best_purchase_option.active_discounts[].discount_end_date.
        Only queried for games that came back on sale, so it's tiny.

Output prices.json keyed by appid -> { price_initial, price_final, discount_pct,
discount_end, scraped_at }. discount_end is null unless the game is on sale with a dated
end. Ended/expired sales are pruned (frontend also collapses past-due sales offline).
Package-derived rows carry three extra keys — price_src:"package", pkg_name, pkg_count —
so the frontend can render them as "from $X" instead of as a firm app price. Rows with no
price at all carry `avail` explaining WHY ("only" = sold only inside a bundle or successor,
with only_name/only_price; "notsold" = nothing purchasable, i.e. delisted; "unknown" =
unpurchasable but a package exists, usually a free app) plus avail_at, the verdict's date.

Ownership (one writer per file):
  scraper.py      -> games.json   (catalog, rating, tags, last_update, release)
  THIS            -> prices.json  (price, discount %, sale end)
  hltb_refresh    -> hltb.json    (static completion times)
  recent_refresh  -> recent.json  (30-day review scores)
Frontend merges all four by appid; QHPP is computed client-side from the merge.

Reads games.json (read-only) for the appid list (and to know which games are free).
"""

import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
GAMES_FILE = HERE / "games.json"          # read-only (owned by scraper.py)
PRICES_FILE = HERE / "prices.json"        # this job's output (committed)

COUNTRY = os.environ.get("QHPP_CC", "US")
COUNTRY_LC = COUNTRY.lower()
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "60"))
CHECKPOINT_SECONDS = 300
TIME_BUFFER = 45

PRICE_BATCH = 100                         # appids per batched price-only appdetails call
GETITEMS_BATCH = 50                       # appids per GetItems call (sale end dates)
STORE_DELAY = 1.6                         # between storefront calls (~200/5min budget)
GETITEMS_DELAY = 1.2
MAX_RETRIES = 4
PAST_SLACK = 120                          # treat end dates this far past as already-ended
AVAIL_TTL = 7 * 86400                     # re-confirm a "not sold" verdict after a week
AVAIL_MAX_PER_RUN = 60                    # cap on the per-app availability calls (§1c)

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
HEADERS = {"User-Agent": "Mozilla/5.0 (steam-qhpp price/sale refresher; github pages dataset builder)",
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
# 1. Batched prices via appdetails?filters=price_overview
# --------------------------------------------------------------------------- #
def fetch_prices(appids):
    """Return {appid: {price_initial, price_final, discount_pct}} for a batch. Games that
    are free or have no price block are returned with nulls/0 so the frontend can clear a
    stale sale. The response is keyed by appid string, each {success, data:{price_overview}}."""
    csv = ",".join(str(a) for a in appids)
    data = get("https://store.steampowered.com/api/appdetails",
               params={"appids": csv, "filters": "price_overview", "cc": COUNTRY_LC, "l": "english"})
    out = {}
    if not isinstance(data, dict):
        return out
    for aid in appids:
        node = data.get(str(aid))
        if not isinstance(node, dict) or not node.get("success"):
            continue
        po = (node.get("data") or {}).get("price_overview")
        if not po:
            # success but no price -> free or unpriced. Record explicit nulls so any prior
            # sale is cleared.
            out[int(aid)] = {"price_initial": None, "price_final": None, "discount_pct": 0}
            continue
        pi = round(po.get("initial", 0) / 100, 2) or None
        pf = round(po.get("final", 0) / 100, 2) or None
        out[int(aid)] = {"price_initial": pi, "price_final": pf,
                         "discount_pct": int(po.get("discount_percent", 0))}
    return out


# --------------------------------------------------------------------------- #
# 1b. Package prices for apps that have no app-level price
# --------------------------------------------------------------------------- #
# Some non-free apps carry no price_overview at all: the store page sells only PACKAGES,
# never the bare app. The big one is Activision's shared Call of Duty launcher (1938090),
# where a single app fronts MW4 / Black Ops 7 / Warzone plus CoD Points, so "the price of
# the app" doesn't exist — appdetails returns success with an empty data block. Those rows
# used to render a bare "—" even though the page clearly shows prices.
#
# GetItems (already batched below for sale dates) does expose them, under purchase_options.
# We take the CHEAPEST qualifying option and mark it price_src="package" so the frontend
# can render it as "from $X" rather than as a definitive app price.
#
# Qualifying is deliberately STRICT: an option counts only if it has a packageid AND sits
# in a NAMED package_group — not "default", not a display_type-1 dropdown. Steam only
# creates named/headed groups when one store page genuinely fronts several products, which
# is exactly the case we want (CoD's "BlackOps7" / "CallofDuty:ModernWarfare4" headings).
# Everything the strictness throws away is something that would have been a WRONG price:
#   * default-group options on delisted apps are the SUCCESSOR product, not this app —
#     Half-Life 2: Deathmatch offers "The Orange Box" ($19.99), Darksiders™ offers
#     "Darksiders Warmastered Edition", ARK: SOTF offers "ARK: Survival Evolved".
#   * default-group options on dead games can be leftover DLC — Street Fighter X Tekken
#     sells only costume packs now, so "cheapest option" would price the game at $12.99.
#   * display_type-1 groups are the "select an option" dropdowns: in-game currency and
#     subscriptions. Without the exclusion CoD would read "from $1.99" for 200 CoD Points.
#   * bundleid options are a BUNDLE that merely contains this game (Horizon Zero Dawn
#     Complete Edition only sells inside the Remastered Bundle).
# A wrong price is worse than none — it feeds QTPD, sorting and the CSV — so anything
# ambiguous keeps its "—".
#
# The same sweep also records WHY an app has no price, as `avail`, so the frontend can say
# something better than a bare "—". Measured over the whole 452-app unpriced set:
#   * 404 have NO purchase option at all  -> "notsold" (pending the packages check below)
#   *  22 sell only inside a bundle       -> "only" (Horizon Zero Dawn Complete Edition is
#      buyable only in the Remastered Bundle, $49.99)
#   *  25 offer only a default-group package — the successor product or leftover DLC — which
#      is the same story from the shopper's side: this app is not sold on its own -> "only"
#   *   1 qualifies for a real package price (Call of Duty).
# "only" carries only_name/only_price for display; it deliberately does NOT set price_final,
# because a bundle's price is not this game's price and would poison QTPD and sorting.
def _demojibake(s):
    """GetItems returns purchase_option_name double-encoded — "Call of Duty®" arrives as
    "Call of Duty\\u00c2\\u00ae", i.e. the UTF-8 bytes of ® read back as latin-1. Undo that
    when it round-trips cleanly; leave the string alone when it doesn't (genuinely
    latin-1-unrepresentable names, which are already correct)."""
    if not s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _cents(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_package_prices(appids):
    """Classify a batch of apps that have no app-level price. Returns {appid: fields} where
    fields is one of:
      * a real package price  — price_initial/price_final/discount_pct/pkg_name/pkg_count
      * avail "only"          — only_name/only_price: not sold on its own, the page's sole
                                purchase option is that bundle/successor product
      * avail "notsold"       — nothing purchasable at all. PROVISIONAL: confirm_notsold()
                                still has to rule out free apps that Steam simply doesn't
                                list a purchase option for."""
    out = {}
    items = getitems(appids)
    for item in items:
        aid = item.get("appid") or item.get("id")
        if aid is None:
            continue
        opts = [p for p in (item.get("purchase_options") or []) if isinstance(p, dict)]
        if not opts:
            out[int(aid)] = {"avail": "notsold"}
            continue
        # The groups a real product can live in: named (has a heading Steam renders on the
        # page), not "default", not a display_type-1 dropdown.
        named = {g.get("name") for g in (item.get("package_groups") or [])
                 if isinstance(g, dict) and g.get("name") not in (None, "", "default")
                 and g.get("display_type") != 1}
        best = None
        n_ok = 0
        for po in opts:
            if not po.get("packageid"):
                continue                       # bundle, or malformed
            if po.get("package_group") not in named:
                continue                       # default group, currency pack, subscription
            final_c = _cents(po.get("final_price_in_cents"))
            if final_c is None or final_c <= 0:
                continue
            n_ok += 1
            if best is None or final_c < int(best.get("final_price_in_cents")):
                best = po
        if best is None:
            # Nothing qualifies as this app's own price, but the page does sell SOMETHING —
            # a bundle containing it, or the successor product. Report the cheapest such
            # option as "only <name>, $X" without ever treating it as this game's price.
            alt = None
            for po in opts:
                c = _cents(po.get("final_price_in_cents"))
                if c is None or c <= 0:
                    continue
                if alt is None or c < int(alt.get("final_price_in_cents")):
                    alt = po
            if alt is None:
                out[int(aid)] = {"avail": "notsold"}
            else:
                out[int(aid)] = {
                    "avail": "only",
                    "only_name": _demojibake((alt.get("purchase_option_name") or "").strip()) or None,
                    "only_price": round(int(alt["final_price_in_cents"]) / 100, 2),
                }
            continue
        final = int(best["final_price_in_cents"])
        try:
            orig = int(best.get("original_price_in_cents") or 0)
        except (TypeError, ValueError):
            orig = 0
        disc = int(best.get("discount_pct") or 0)
        if orig <= final:                      # not on sale (or Steam sent no original)
            orig, disc = final, 0
        out[int(aid)] = {
            "price_initial": round(orig / 100, 2),
            "price_final": round(final / 100, 2),
            "discount_pct": disc,
            "pkg_name": _demojibake((best.get("purchase_option_name") or "").strip()) or None,
            "pkg_count": n_ok,
        }
    return out


# --------------------------------------------------------------------------- #
# 1c. Confirming "not sold"
# --------------------------------------------------------------------------- #
# GetItems reporting zero purchase options is NOT enough to call a game delisted: a free
# app has nothing to *purchase* either, and Steam's own is_free flag is wrong often enough
# to be useless here (It Takes Two Friend's Pass and Animal Jam are free and obtainable,
# yet both come back is_free=False with no purchase option). appdetails' `packages` list
# separates them — a delisted game has NO packages at all, while a free app still has the
# package that grants it. On a 26-app sample, 4 (15%) would have been mislabelled without
# this check, so it is worth the calls.
#
# It costs one call per app (appdetails only batches with filters=price_overview; asking
# for packages across several appids is a hard 400), so the answer is CACHED in prices.json
# as avail/avail_at and only a slice is re-checked per run. Availability changes on the
# order of months, the bucket is ~400 apps, and the job runs several times a day, so
# AVAIL_MAX_PER_RUN=60 still refreshes the whole set roughly daily.
def confirm_notsold(appid):
    """True if the app has no packages at all (delisted / never sold), False if it has one
    (free app, region-locked, etc.), None if Steam didn't answer — caller leaves it be."""
    data = get("https://store.steampowered.com/api/appdetails",
               params={"appids": str(appid), "filters": "packages", "cc": COUNTRY_LC})
    node = (data or {}).get(str(appid))
    if not isinstance(node, dict) or not node.get("success"):
        return None
    return not ((node.get("data") or {}).get("packages") or [])


def load_prev_avail():
    """Availability facts from the existing prices.json, so a rebuild doesn't lose the
    classification for the ~340 apps this run won't re-check. {appid_str: (avail, at)}."""
    if not PRICES_FILE.exists():
        return {}
    try:
        d = json.loads(PRICES_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    out = {}
    for k, v in (d.get("prices") or {}).items():
        if isinstance(v, dict) and v.get("avail"):
            out[k] = (v["avail"], int(v.get("avail_at") or 0))
    return out


# --------------------------------------------------------------------------- #
# 2. Batched sale end-dates via GetItems
# --------------------------------------------------------------------------- #
# Every key Steam has been observed to return a sale-end unix timestamp under, across
# the various GetItems schema revisions. We check all of them so a schema tweak on
# Valve's side can't silently null us out again.
_END_KEYS = ("discount_end_date", "discount_end", "end_date", "ends_at", "expiry_time")


def _coerce_ts(v):
    """Return a plausible future-ish unix timestamp int, or None. Accepts ints, numeric
    strings, and {'seconds': ...} / {'value': ...} wrapper objects Steam sometimes uses."""
    if isinstance(v, dict):
        v = v.get("seconds") or v.get("value") or v.get("time")
    if v in (None, "", 0, "0"):
        return None
    try:
        ts = int(v)
    except (TypeError, ValueError):
        return None
    # sanity window: after 2017-07 and before 2100. Rejects millisecond values,
    # release years, and other garbage.
    return ts if 1_500_000_000 < ts < 4_100_000_000 else None


def _iter_purchase_options(item):
    """Yield every purchase-option dict, regardless of which container Steam used.
    Different GetItems responses put discounts under best_purchase_option,
    purchase_options[], or (rarely) a bare active_discounts[] at the item root."""
    bpo = item.get("best_purchase_option")
    if isinstance(bpo, dict):
        yield bpo
    for po in (item.get("purchase_options") or []):
        if isinstance(po, dict):
            yield po
    # some responses omit the wrapper and hang active_discounts off the item itself
    if isinstance(item.get("active_discounts"), list):
        yield item


def _extract_end_date(item):
    """Robustly pull the earliest sale-end timestamp from any purchase-option shape.
    Returns None if the item carries no dated discount (permanent price cut, or Steam
    simply didn't send an end date)."""
    ends = []
    for po in _iter_purchase_options(item):
        discounts = po.get("active_discounts")
        if not isinstance(discounts, list):
            continue
        for d in discounts:
            if not isinstance(d, dict):
                continue
            for k in _END_KEYS:
                ts = _coerce_ts(d.get(k))
                if ts is not None:
                    ends.append(ts)
                    break  # one hit per discount is enough
    return min(ends) if ends else None


def getitems(appids):
    """One batched GetItems call -> list of store_item dicts (empty list on failure).
    Shared by the package-price pass and the sale-end-date pass; both need the same
    basic-info + all-purchase-options payload."""
    payload = {
        "ids": [{"appid": int(a)} for a in appids],
        "context": {"country_code": COUNTRY, "language": "english"},
        # include_basic_info + include_all_purchase_options are what actually populate the
        # purchase-option / active_discounts blocks that carry the sale end date. With both
        # off (the previous state) the response came back with no discount info at all, so
        # every end date resolved to null — the silent bug that made every row show a flat
        # "on sale". Keep the rest off to stay lean.
        "data_request": {"include_basic_info": True, "include_assets": False,
                         "include_release": False, "include_tag_count": 0,
                         "include_reviews": False, "include_platforms": False,
                         "include_all_purchase_options": True},
    }
    params = {"input_json": json.dumps(payload, separators=(",", ":"))}
    if STEAM_API_KEY:
        params["key"] = STEAM_API_KEY
    data = get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/", params=params)
    if not isinstance(data, dict):
        return []
    items = ((data.get("response") or {}).get("store_items")) or []
    # Diagnostic: set QHPP_DUMP_GETITEMS=1 to print the raw JSON of the first batch's
    # first few items, then exit. Run this once via the workflow's manual dispatch to see
    # the exact field Steam uses, from a runner that can actually reach the API.
    if os.environ.get("QHPP_DUMP_GETITEMS") == "1":
        log("=== RAW GetItems DUMP (first 3 items) ===")
        for item in items[:3]:
            log(json.dumps(item, indent=2)[:4000])
            log("---")
        log(f"=== _extract_end_date results: "
            f"{[(it.get('appid') or it.get('id'), _extract_end_date(it)) for it in items[:10]]}")
        sys.exit(0)
    return items


def fetch_end_dates(appids):
    out = {}
    for item in getitems(appids):
        aid = item.get("appid") or item.get("id")
        if aid is None:
            continue
        end = _extract_end_date(item)
        if end is not None:
            out[int(aid)] = end
    return out


# --------------------------------------------------------------------------- #
# I/O + git
# --------------------------------------------------------------------------- #
def load_appids():
    """All non-free appids from games.json (free games have no price to refresh)."""
    if not GAMES_FILE.exists():
        return []
    try:
        d = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if d.get("sample"):
        return []
    return [int(g["appid"]) for g in d.get("games", []) if not g.get("is_free")]


def save_prices(prices):
    PRICES_FILE.write_text(json.dumps(
        {"generated_at": int(time.time()), "country": COUNTRY,
         "count": len(prices), "prices": {str(k): v for k, v in prices.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")


def git_checkpoint(msg):
    if not IN_ACTIONS:
        return
    try:
        subprocess.run(["git", "add", "prices.json"], check=False)
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
def main():
    start = time.time()
    now = int(start)
    appids = load_appids()
    if not appids:
        log("No priced games in games.json (or only sample data). Writing empty prices.json.")
        save_prices({})
        git_checkpoint("prices: nothing to refresh")
        return 0

    log(f"Priced games to refresh: {len(appids)} "
        f"({math.ceil(len(appids)/PRICE_BATCH)} price batches)")

    prices = {}                # rebuilt fresh each run
    budget = RUN_MINUTES * 60
    last_commit = time.time()
    onsale = []                # appids that came back discounted -> need an end date

    # --- pass 1: batched prices for the whole catalog ---
    for i in range(0, len(appids), PRICE_BATCH):
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached during price pass; wrapping up.")
            break
        chunk = appids[i:i + PRICE_BATCH]
        got = fetch_prices(chunk)
        time.sleep(STORE_DELAY)
        for aid, p in got.items():
            prices[str(aid)] = {**p, "discount_end": None, "scraped_at": now}
            if (p.get("discount_pct") or 0) > 0:
                onsale.append(aid)
        if i % (PRICE_BATCH * 5) == 0:
            log(f"  [prices {min(i+PRICE_BATCH, len(appids))}/{len(appids)}] {len(onsale)} on sale so far")
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_prices(prices)
            git_checkpoint(f"prices: {len(prices)} priced (checkpoint)")
            last_commit = time.time()

    # --- pass 1b: package prices + availability for apps appdetails gave no price for ---
    # ~450 of the catalog: package-only storefronts (the CoD launcher) mixed with delisted
    # games. ~10 batched calls, so it costs nothing next to the price pass above.
    unpriced = [int(k) for k, p in prices.items() if p.get("price_final") is None]
    log(f"Package-price pass for {len(unpriced)} apps with no app-level price "
        f"({math.ceil(len(unpriced)/GETITEMS_BATCH)} batches)")
    n_pkg = n_only = 0
    pending = []               # provisional "notsold" -> needs the pass-1c confirmation
    for i in range(0, len(unpriced), GETITEMS_BATCH):
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached during package-price pass; wrapping up.")
            break
        chunk = unpriced[i:i + GETITEMS_BATCH]
        got = fetch_package_prices(chunk)
        time.sleep(GETITEMS_DELAY)
        for aid, p in got.items():
            key = str(aid)
            if key not in prices:
                continue
            if p.get("avail") == "notsold":
                pending.append(aid)
                continue
            prices[key].update(p)
            if p.get("avail") == "only":
                n_only += 1
                continue
            prices[key]["price_src"] = "package"
            n_pkg += 1
            if (p.get("discount_pct") or 0) > 0:
                onsale.append(aid)
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_prices(prices)
            git_checkpoint(f"prices: {len(prices)} priced, {n_pkg} from packages (checkpoint)")
            last_commit = time.time()
    log(f"  resolved {n_pkg} package-only prices, {n_only} sold only inside something else, "
        f"{len(pending)} with nothing purchasable")

    # --- pass 1c: confirm the "nothing purchasable" verdicts (§1c) ---
    # Cached in prices.json and rotated: reuse any verdict younger than AVAIL_TTL, spend the
    # per-run call budget on the staleset, oldest first. Apps we can't get to keep whatever
    # the last run concluded, so the labels stay put instead of flickering.
    prev = load_prev_avail()
    fresh = stale = 0
    for aid in pending:
        key = str(aid)
        got = prev.get(key)
        if got and got[0] in ("notsold", "unknown") and now - got[1] < AVAIL_TTL:
            prices[key]["avail"] = got[0]
            prices[key]["avail_at"] = got[1]
            fresh += 1
    todo = [a for a in pending if "avail" not in prices[str(a)]]
    todo.sort(key=lambda a: prev.get(str(a), ("", 0))[1])          # oldest verdict first
    todo = todo[:AVAIL_MAX_PER_RUN]
    log(f"Availability pass: {fresh} cached verdicts reused, confirming {len(todo)} "
        f"(of {len(pending) - fresh} stale)")
    n_notsold = 0
    for aid in todo:
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached during availability pass; wrapping up.")
            break
        verdict = confirm_notsold(aid)
        time.sleep(STORE_DELAY)
        if verdict is None:
            continue                       # Steam didn't answer; leave the row unlabelled
        stale += 1
        prices[str(aid)]["avail"] = "notsold" if verdict else "unknown"
        prices[str(aid)]["avail_at"] = now
        if verdict:
            n_notsold += 1
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_prices(prices)
            git_checkpoint(f"prices: {len(prices)} priced, {n_notsold} not sold (checkpoint)")
            last_commit = time.time()
    log(f"  confirmed {n_notsold} not sold, {stale - n_notsold} still buyable some other way")

    # --- pass 2: sale end-dates only for the on-sale subset ---
    log(f"Fetching sale end-dates for {len(onsale)} on-sale games "
        f"({math.ceil(len(onsale)/GETITEMS_BATCH)} batches)")
    n_dated = 0
    for i in range(0, len(onsale), GETITEMS_BATCH):
        if budget - (time.time() - start) < TIME_BUFFER:
            log("Time budget reached during sale-date pass; wrapping up.")
            break
        chunk = onsale[i:i + GETITEMS_BATCH]
        ends = fetch_end_dates(chunk)
        time.sleep(GETITEMS_DELAY)
        for aid, end in ends.items():
            if end <= now - PAST_SLACK:
                continue                  # already ended -> leave discount_end null (prune)
            key = str(aid)
            if key in prices:
                prices[key]["discount_end"] = end
                n_dated += 1
        if time.time() - last_commit > CHECKPOINT_SECONDS:
            save_prices(prices)
            git_checkpoint(f"prices: {len(prices)} priced, {n_dated} sale dates (checkpoint)")
            last_commit = time.time()

    save_prices(prices)
    git_checkpoint(f"prices: {len(prices)} priced, {len(onsale)} on sale, {n_dated} dated")
    log(f"\nDone. Refreshed {len(prices)} prices; {n_pkg} from packages; {n_only} sold only "
        f"inside something else; {n_notsold} confirmed not sold; {len(onsale)} on sale; "
        f"{n_dated} with a live sale end-date. prices.json updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

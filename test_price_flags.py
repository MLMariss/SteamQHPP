#!/usr/bin/env python3
"""Regression tests for free-to-keep-promo reconciliation (scraper.py + price_and_sale.py).

A promo makes Steam's appdetails self-contradictory — is_free true and discount_percent
100 on top of the FULL price — and stored verbatim that snapshot outlives the promo
(Moonlighter 606150, Breathedge 738520). Pure-logic only: no network, no git, no disk."""
import sys, types

# Stub `requests` so both modules import without the dependency present.
if "requests" not in sys.modules:
    m = types.ModuleType("requests")
    m.Session = lambda: types.SimpleNamespace(
        headers=type("H", (), {"update": lambda s, d: None})(),
        cookies=type("C", (), {"update": lambda s, d: None})(),
        get=lambda *a, **k: None)
    m.RequestException = Exception
    m.Response = type("Response", (), {})
    sys.modules["requests"] = m

import scraper as S

fails = []

def check(name, cond):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        fails.append(name)

print("\n== reconcile_price_flags: the promo signature ==")
# What appdetails returned for Moonlighter while it was free to keep.
check("free + 100% off at full price -> paid, no discount",
      S.reconcile_price_flags(True, 19.99, 19.99, 100) == (False, 0))
check("free + 100% off at full price (Breathedge) -> paid, no discount",
      S.reconcile_price_flags(True, 24.99, 24.99, 100) == (False, 0))

print("\n== reconcile_price_flags: honest records are untouched ==")
check("ordinary sale survives",              S.reconcile_price_flags(False, 19.99, 9.99, 50) == (False, 50))
check("full-price game survives",            S.reconcile_price_flags(False, 19.99, 19.99, 0) == (False, 0))
check("real free game (no price) survives",  S.reconcile_price_flags(True, None, None, 0) == (True, 0))
check("free game priced 0 survives",         S.reconcile_price_flags(True, None, 0, 0) == (True, 0))
# Capcom Arcade Stadium (1515950): genuinely free, and its store page really does sell a
# discounted pack at the app level. Both halves are true, so neither is rewritten.
check("free app with a real package sale keeps both",
      S.reconcile_price_flags(True, 59.99, 14.99, 75) == (True, 75))
check("100% off with a final price of 0 stays 100% off",
      S.reconcile_price_flags(True, 19.99, None, 100) == (True, 100))

print("\n== reconcile_price_flags: partial contradictions ==")
check("priced game flagged free (no discount) -> paid",
      S.reconcile_price_flags(True, 9.99, 9.99, 0) == (False, 0))
check("discount claimed but final == initial -> no discount",
      S.reconcile_price_flags(False, 19.99, 19.99, 40) == (False, 0))
check("discount claimed but final > initial -> no discount",
      S.reconcile_price_flags(False, 9.99, 19.99, 40) == (False, 0))

print("\n== promo_residue: which stored records get re-scraped first ==")
check("Moonlighter's stored record is residue",
      S.promo_residue({"is_free": True, "price_initial": 19.99,
                       "price_final": 19.99, "discount_pct": 100}))
check("an ordinary sale is not residue",
      not S.promo_residue({"is_free": False, "price_initial": 19.99,
                           "price_final": 9.99, "discount_pct": 50}))
check("a real free game is not residue",
      not S.promo_residue({"is_free": True, "price_initial": None,
                           "price_final": None, "discount_pct": 0}))
check("a full-price game is not residue",
      not S.promo_residue({"is_free": False, "price_initial": 19.99,
                           "price_final": 19.99, "discount_pct": 0}))
check("free app with a real package sale is not residue",
      not S.promo_residue({"is_free": True, "price_initial": 59.99,
                           "price_final": 14.99, "discount_pct": 75}))
check("missing price fields don't crash",
      not S.promo_residue({"is_free": True}))

print("\n== price_and_sale: the price job can still see promo records ==")
import price_and_sale as P
GAMES = {"games": [
    {"appid": 1, "is_free": False, "price_initial": 19.99},      # ordinary paid game
    {"appid": 2, "is_free": True,  "price_initial": None},       # genuine free-to-play
    {"appid": 3, "is_free": True,  "price_initial": 19.99},      # promo residue
]}
import json, pathlib, tempfile
tmp = pathlib.Path(tempfile.mkdtemp()) / "games.json"
tmp.write_text(json.dumps(GAMES), encoding="utf-8")
P.GAMES_FILE = tmp
ids = P.load_appids()
check("paid game is refreshed",             1 in ids)
check("genuine free game is still skipped", 2 not in ids)
check("promo residue is refreshed (this is what let it fossilise)", 3 in ids)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)

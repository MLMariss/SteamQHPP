#!/usr/bin/env python3
"""Regression tests for the screenshot layer's parser and sharding (shots.py).

Pure-logic only: no network, no git, no repo writes. These matter more than the usual
regression suite because the layer's INPUT SHAPE HAS NEVER BEEN SEEN — Steam is
unreachable from a dev sandbox, so extract_shots is written to tolerate a range of
plausible shapes (ARCHITECTURE.md §2.2). Each case below pins one of those tolerances, so
that when the dump run finally shows the real payload it is obvious which assumption held
and which did not.
"""
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

# Stub `requests` so shots imports without the dependency present.
if "requests" not in sys.modules:
    m = types.ModuleType("requests")
    m.Session = lambda: types.SimpleNamespace(
        headers=type("H", (), {"update": lambda s, d: None})(),
        get=lambda *a, **k: None, head=lambda *a, **k: None)
    m.RequestException = Exception
    sys.modules["requests"] = m

import shots as S

fails = []


def check(name, cond):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        fails.append(name)


def shots_case(name, item, want_files, want_mature):
    got = S.extract_shots(item)
    ok = got == (want_files, want_mature)
    check(name if ok else f"{name}  (got {got}, want {(want_files, want_mature)})", ok)


print("\nextract_shots — the expected shape")
shots_case("ordinal decides order, capped at MAX_SHOTS",
           {"screenshots": {"all_ages_screenshots": [
               {"filename": "ss_e.jpg", "ordinal": 4}, {"filename": "ss_a.jpg", "ordinal": 0},
               {"filename": "ss_c.jpg", "ordinal": 2}, {"filename": "ss_b.jpg", "ordinal": 1},
               {"filename": "ss_d.jpg", "ordinal": 3}]}},
           ["ss_a.jpg", "ss_b.jpg", "ss_c.jpg", "ss_d.jpg"][:S.MAX_SHOTS], False)
shots_case("entries with no ordinal keep source order",
           {"screenshots": {"all_ages_screenshots": [{"filename": "ss_1.jpg"}, {"filename": "ss_2.jpg"}]}},
           ["ss_1.jpg", "ss_2.jpg"], False)
shots_case("duplicates collapse, first position wins",
           {"screenshots": {"all_ages_screenshots": [
               {"filename": "ss_s.jpg", "ordinal": 0}, {"filename": "ss_s.jpg", "ordinal": 1}]}},
           ["ss_s.jpg"], False)

print("\nextract_shots — filename normalisation")
shots_case("full URL: host dropped to base-relative, ?t= cache-buster stripped",
           {"screenshots": {"all_ages_screenshots": [{"path_thumbnail":
            "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/620/ss_x.600x338.jpg?t=176"}]}},
           ["620/ss_x.600x338.jpg"], False)
shots_case("unknown host layout degrades to the bare filename",
           {"screenshots": {"all_ages_screenshots": [{"filename": "https://example.net/w/p/ss_z.jpg"}]}},
           ["ss_z.jpg"], False)
shots_case("non-image values are dropped, not stored",
           {"screenshots": {"all_ages_screenshots": [{"filename": "movie.webm"}, {"filename": "ss_r.jpg"}]}},
           ["ss_r.jpg"], False)

print("\nextract_shots — adult split (the gate must not be bypassable)")
shots_case("mature-only is declined and reported as such",
           {"screenshots": {"all_ages_screenshots": [],
                            "mature_content_screenshots": [{"filename": "ss_m.jpg", "ordinal": 0}]}},
           [], True)
shots_case("a renamed all-ages key still beats the mature set",
           {"screenshots": {"mature_content_screenshots": [{"filename": "ss_m.jpg"}],
                            "screenshots_v2": [{"filename": "ss_n.jpg", "ordinal": 0}]}},
           ["ss_n.jpg"], False)

print("\nextract_shots — shapes we have not seen")
shots_case("bare list of dicts instead of the named keys",
           {"screenshots": [{"filename": "ss_p.jpg"}, {"filename": "ss_q.jpg"}]},
           ["ss_p.jpg", "ss_q.jpg"], False)
shots_case("bare list of strings", {"screenshots": ["ss_p.jpg", "ss_q.jpg"]},
           ["ss_p.jpg", "ss_q.jpg"], False)
shots_case("scalar siblings are ignored, not walked into",
           {"screenshots": {"screenshot_count": 5, "all_ages_screenshots": [{"filename": "ss_k.jpg"}]}},
           ["ss_k.jpg"], False)
shots_case("no screenshots block at all", {"appid": 1}, [], False)
shots_case("present but empty is a plain miss, not a decline",
           {"screenshots": {"all_ages_screenshots": [], "mature_content_screenshots": []}}, [], False)

print("\nsharding")
tmp = Path(tempfile.mkdtemp())
real_dir = S.SHOTS_DIR
try:
    S.SHOTS_DIR = tmp / "shots"
    hits = {str(a): [f"ss_{a}.jpg"] for a in range(1000, 1400)}
    S.save_shots(hits, {S.shard_of(k) for k in hits})
    check("round-trips through the shard set unchanged", S.load_shots() == hits)
    check("every row lands in the shard its appid names", all(
        int(a) % S.SHARDS == json.loads(p.read_text())["_shard"]
        for p in S.SHOTS_DIR.iterdir() for a in json.loads(p.read_text())["shots"]))

    # A checkpoint must not rewrite 64 shards (≈25MB) to record a handful of new rows.
    before = {p.name: p.read_bytes() for p in S.SHOTS_DIR.iterdir()}
    key = "1234"
    hits[key] = ["ss_new.jpg"]
    S.save_shots(hits, {S.shard_of(key)})
    changed = [p.name for p in S.SHOTS_DIR.iterdir() if before.get(p.name) != p.read_bytes()]
    check("a one-row change rewrites exactly one shard", changed == [f"shard_{S.shard_of(key):02d}.json"])
    check("and the changed row is what comes back", S.load_shots()[key] == ["ss_new.jpg"])
    check("shards carry the CDN base the frontend joins against", all(
        json.loads(p.read_text()).get("base") for p in S.SHOTS_DIR.iterdir()))
finally:
    S.SHOTS_DIR = real_dir
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all passed'}")
sys.exit(1 if fails else 0)

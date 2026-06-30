# SteamQHPP — Architecture & Maintenance Guide

A complete technical reference for the SteamQHPP project: what every file does, how
the pieces fit together, why the architecture is shaped the way it is, and how to
operate and extend it.

> This is the deep-dive companion to `README.md`. The README is the short "what is
> this / how do I set it up" intro; this document is the engineering reference for
> anyone (including future-you) maintaining or extending the system.

---

## 1. What this is

SteamQHPP ranks Steam games by **QHPP — Quality Hours Per Price**:

```
QHPP = (average HowLongToBeat hours × rating %) ÷ price
```

Higher QHPP = more quality-adjusted playtime per dollar. The idea is to surface games
that give a lot of well-reviewed play time for the money, and to make that browsable,
sortable, and filterable.

It runs **entirely on GitHub Pages + GitHub Actions** — no server, no database, no
proxy. A set of scheduled Actions scrape Steam (and HowLongToBeat, and SteamSpy)
server-side and commit the results to the repo as JSON. A static `index.html` reads
those JSON files in the browser and does all the merging, ranking, and filtering
client-side. Cost is $0: Actions is free and unlimited on public repos, and Pages
hosts the static site for free.

The frontend **never calls Steam directly** — it can't, because Steam sends no CORS
headers — so every network fetch happens inside an Action, and the browser only ever
reads the committed JSON.

---

## 2. The core architectural principle: ONE WRITER PER FILE

This is the single most important thing to understand about the codebase. **Every
data file is owned by exactly one job. No two jobs ever write the same file.**

### Why it exists

Multiple GitHub Actions run on independent schedules and all need to commit to the
same repo on the `main` branch. If two of them wrote the *same* file, their commits
would collide on push — one would be rejected, and a naive retry could clobber the
other's work or get stuck in a rebase conflict. This actually happened early in the
project (detached-HEAD states and race conditions across concurrent workflows) and
was painful to debug.

The fix is structural rather than defensive: if jobs write **different** files, a
`git pull --rebase` before every push *always* applies cleanly, because there are no
overlapping changes to reconcile. Concurrent commits to disjoint files merge
automatically.

### How it's enforced

Each data layer lives in its own file with a single owner:

| File           | Sole writer          | Contents                                                        |
|----------------|----------------------|-----------------------------------------------------------------|
| `games.json`   | `scraper.py`         | Catalog: title, URL, rating %, review count, release date, genre fallback, `last_update_ts`. Also a base `price_*`/`discount_pct` snapshot from the scrape. |
| `catalog.json` | `scraper.py`         | Scraper state: cursor, pending (waiting-room), skip-list, seeds ledger, force-refresh list, last sync. |
| `prices.json`  | `price_and_sale.py`  | The fast-changing pricing layer: `price_initial`, `price_final`, `discount_pct`, `discount_end`, `scraped_at`. **Source of truth for price.** |
| `hltb.json`    | `hltb_refresh.py`    | Static HowLongToBeat completion times + estimated fills.        |
| `tags.json`    | `tags_refresh.py`    | SteamSpy user tags per appid.                                   |
| `recent.json`  | `recent_refresh.py`  | 30-day rolling "recent reviews" score per appid.               |
| `sales.json`   | *(legacy)*           | Older standalone sale-end-date file, superseded by `prices.json`'s `discount_end`. Retained for back-compat; not actively required. |

The **frontend merges all of these by appid at load time** and computes QHPP from the
merged record. QHPP is never stored server-side — it's derived in the browser from
whatever the current merge produces, so changing the formula or the chosen HLTB
metric is instant and requires no re-scrape.

> **Rule for any future change:** if you add a new data source, give it a **new file
> and a new owner**. Never add a second writer to an existing file. The one exception
> is a logically atomic fact owned together — e.g. price + discount % + sale end live
> in `prices.json` because they're "what does this cost right now" and must update
> together; splitting them would let two jobs disagree about whether a game is on sale.

---

## 3. The pipeline at a glance

```
                         ┌────────────────────────────────────────────┐
                         │            GitHub Actions (cron)            │
                         └────────────────────────────────────────────┘

  scraper.py ─────────────► games.json   ┐
  (catalog, rating, release)             │
  catalog.json (state)                   │
                                         │
  price_and_sale.py ──────► prices.json  │
  (price, discount, sale end)            │     all merged by appid,
                                         ├──►  client-side, in the browser,
  hltb_refresh.py ────────► hltb.json    │     by index.html  →  QHPP computed
  (completion times + est)               │     via computeQ()
                                         │
  tags_refresh.py ────────► tags.json    │
  (SteamSpy user tags)                   │
                                         │
  recent_refresh.py ──────► recent.json  ┘
  (30-day review trend)

                                  │
                                  ▼
                         GitHub Pages serves
                         index.html + *.json
                                  │
                                  ▼
                            User's browser
```

Each job reads `games.json` **read-only** to learn which appids exist, then writes
only its own file. The main scraper is the only thing that discovers *new* games; the
refreshers enrich games the scraper has already found.

---

## 4. File-by-file reference

### 4.1 `scraper.py` — the catalog accumulator

The heart of the system. Builds up `games.json` over many runs and owns the scraper
state in `catalog.json`.

**What each run does:**

1. **Enumerates the universe** via Steam's `IStoreService/GetAppList` (needs a free
   Web API key) — a clean, games-only, appid-ordered list with a per-app
   `last_modified` timestamp. Falls back to the keyless `ISteamApps/GetAppList/v2`
   if no key is set (lists all app types, no change timestamps).

2. **Reconciles seeds** (see §5) — pulls priority appids from `seeds.txt` into the
   work queue.

3. **Selects work** in priority order (`select_work`):
   - **Refresh** stored games whose `last_modified` moved past when we last scraped
     them, or that are flagged in `force_refresh`.
   - **Promote** games from the pending waiting-room whose release date has now passed.
   - **Priority** seeds from the ledger.
   - **New frontier** — games never seen yet, newest-appid-first (`NEW_ORDER`).

4. **Builds each record** (`build_record`): fetches `appdetails` (price, release,
   genre fallback), `appreviews` (rating %, review count), and the News API
   (`last_update_ts`). Reviews and news are fired concurrently via a thread pool to
   cut per-game latency. **HLTB and SteamSpy tags are NOT fetched here** — they were
   the per-game bottleneck and now live in their own jobs.

5. **Runs on a time budget** (`RUN_MINUTES`, default 180) and **git-commits progress
   every ~10 minutes** (`CHECKPOINT_SECONDS`), so hitting the 6-hour Actions wall
   never loses work. It stops `TIME_BUFFER` seconds before the budget to commit
   cleanly.

**Released-only with a waiting room:** only games with a concrete past release date
are stored as real records. Unreleased games go to `catalog["pending"]` (one cheap
`appdetails` probe) and are promoted automatically once their release date passes.
Nothing is ever permanently skipped for being unreleased.

**Key config (top of file):**

| Constant             | Default     | Meaning                                                       |
|----------------------|-------------|---------------------------------------------------------------|
| `RUN_MINUTES` (env)  | 180         | Scrape budget per run.                                         |
| `STEAM_DELAY`        | 1.5 s       | Between storefront calls (~200 req / 5 min per IP, shared by appdetails + appreviews). |
| `WEBAPI_DELAY`       | 1.0 s       | Between GetAppList pages.                                      |
| `NEWS_DELAY`         | 0.3 s       | Between News API calls (huge separate budget).                |
| `CHECKPOINT_SECONDS` | 600         | Commit progress at least this often.                          |
| `NEW_ORDER`          | `"newest"`  | New-coverage order: newest appid first, or `"oldest"`.        |
| `REFRESH_DAYS`       | 7           | Fallback refresh age, only when no API key (no `last_modified`). |
| `SEED_RESOLVE_TTL`   | 24 h        | Live term/URL seeds re-resolve at most once per day.          |

**Rate-limit note:** Steam's storefront is ~200 requests per 5 minutes per IP, and
that budget is **shared** between `appdetails` and `appreviews`. Don't lower
`STEAM_DELAY` much or you'll trigger 429s and a 5-minute 403 cooldown. The News API
(`api.steampowered.com`) is a *separate*, much larger budget, which is why update
detection is cheap.

### 4.2 `price_and_sale.py` — the pricing layer

Owns `prices.json`: current price, discount %, and sale end-date — the fast-changing
"what does this cost right now" facts. The main scraper does **not** write these (they
change far more often than the catalog, and isolating them keeps the slow scrape lean
and collision-free).

**Two cheap endpoints, both batched:**

1. **Prices** — `appdetails?filters=price_overview&appids=<CSV>`. This is the *one*
   `appdetails` variant Valve still lets you **batch**: pass many comma-separated
   appids, get `price_overview` for all of them in a single call. (Full `appdetails`
   has been one-appid-only since 2015; price-only is the exception.) So the entire
   ~17k-game priced catalog refreshes in `ceil(N / PRICE_BATCH)` calls instead of N.

2. **Sale end dates** — `IStoreBrowseService/GetItems/v1` (batched), reading
   `best_purchase_option.active_discounts[].discount_end_date`. Only queried for the
   subset that came back on sale in step 1, so it's tiny.

`discount_end` is null unless the game is on sale with a dated end. Expired sales are
pruned (and the frontend also collapses past-due sales offline — see §6).

**Key config:** `PRICE_BATCH = 100` (appids per price call), `GETITEMS_BATCH = 50`
(appids per sale-date call), `STORE_DELAY = 1.6 s`, `GETITEMS_DELAY = 1.2 s`,
`RUN_MINUTES = 60`. Currency via `QHPP_CC` env (default `US` → USD).

### 4.3 `hltb_refresh.py` — HowLongToBeat completion times

Owns `hltb.json`. Fetches each game's main / main+extras / completionist times from
howlongtobeat.com **once**, since completion times are static. This was historically
the slowest part of the whole pipeline (2–10 s per game, sometimes hanging), which is
why it was pulled out of the main scraper into its own slow background job.

It only fetches games it has never resolved (`appid not in hltb`), and records a
genuine no-match as a blank entry so it doesn't re-search forever. It hits
howlongtobeat.com, **not** Steam, so it doesn't compete for the storefront rate
budget — safe to run near-continuously.

**The estimation layer (added later — see §7 for the full design):** when HLTB only
has 1 or 2 of the 3 times, the missing ones are filled from the genre-average ratio
between the three, so the `avg` (which QHPP rides on) isn't skewed. Estimation logic
lives in the shared `hltb_estimate.py` module.

**Key config:** `HLTB_DELAY = 0.6 s`, `HLTB_MIN_SIMILARITY = 0.65` (title-match
threshold), `RUN_MINUTES = 120`, `CHECKPOINT_SECONDS = 300`.

### 4.4 `hltb_estimate.py` — shared HLTB estimation logic

Not a job — a **shared module** imported by both `hltb_refresh.py` (live, for new
games) and `hltb_backfill.py` (one-time sweep). Centralizing it means the two paths
can never disagree. Full design in §7.

### 4.5 `tags_refresh.py` — SteamSpy user tags

Owns `tags.json`. SteamSpy was the slowest call left in the main scrape loop (~3–4 s
even without erroring), so it moved to its own job. Tags are effectively static (they
drift slowly as users vote), so each game is fetched once then left alone. If SteamSpy
has no tags for a game, the frontend falls back to the Steam store "genres" the main
scraper still records on the game record — so tags are never blank.

**Key config:** `TOP_TAGS = 8`, `STEAMSPY_DELAY = 1.1 s` (SteamSpy asks for ~1 req/sec),
`RUN_MINUTES = 120`.

### 4.6 `recent_refresh.py` — recent-review trend

Owns `recent.json`: each game's *recent* (last-30-day) Steam review score, so the
frontend can show a recent-vs-all-time trend (improving / stable / declining).

The recent score is a 30-day rolling window, so it drifts daily even with no new
reviews — and we can't keep ~90k games perfectly fresh within the rate limit. So it
spends calls where reviews are actually likely to be moving:

- **Cooldown** (`RECENT_COOLDOWN_DAYS = 4`): never re-check a score younger than this.
- **Update-priority:** recently *patched* games (from `last_update_ts`) jump the queue
  — a patch is exactly when reviews swing. (`UPDATE_ACTIVE_DAYS = 90`.)
- **No-update games** get a much longer cooldown (`NOUPDATE_COOLDOWN_DAYS = 30`),
  checked rarely but never skipped forever.
- **Low-volume de-prioritized:** games with `< RECENT_MIN_COUNT` (10) recent reviews
  are noisy, so they sink in the queue.
- **Oldest-first tiebreak** so everything eventually refreshes.

It reproduces Steam's exact "Recent Reviews" definition from the public
`appreviewhistogram` endpoint (summing daily up/down buckets over the trailing 30
days), shown only once a game is `MIN_AGE_DAYS = 45` old — so the number matches the
store page with no fragile HTML scraping.

### 4.7 `index.html` — the frontend

A single static page (~1,400 lines, no build step, no framework) that:

1. **Fetches all the JSON layers** (`games.json`, `prices.json`, `hltb.json`,
   `tags.json`, `recent.json`) with `cache: no-store`.
2. **Merges them by appid** into one game object per game (`game.hltb_main`,
   `game.price_final`, `game.recent_pct`, etc.). `prices.json` overrides the base
   price snapshot in `games.json`; `tags.json` overrides the genre fallback.
3. **Computes QHPP client-side** via `computeQ(g, basis)` from the merged fields,
   using whichever HLTB metric is selected (`hoursFor`) and whichever price basis
   (before/after discount).
4. **Expires ended sales offline** (`expireSaleIfEnded`) — a sale whose `discount_end`
   has passed collapses to base price with no scraping.
5. **Renders, sorts, filters, paginates** with infinite scroll.

**Frontend state defaults:** sort by QHPP descending, after-discount price basis,
`avg` HLTB metric, min rating any, min reviews 100, page size 100. All filter/sort
state is reflected in the URL so views are shareable.

**Filters:** title search · on-sale-only · min rating (any/70+/80+/90+) · max price ·
tag click-to-filter · sort by any column.

### 4.8 One-off / maintenance scripts

These are run-once utilities (idempotent — safe to re-run; they no-op on clean data):

- **`hltb_backfill.py`** — one-time sweep that rewrote every existing `hltb.json`
  entry to add `raw`/`est`/`fetched_at` and fix the historically-skewed `avg`. See §7.
  Already run; retained for reference / re-runs.
- **`backfill_updates.py`** — one-off fill of `last_update_ts` for games scraped
  before the scraper started recording it. Uses the News API (cheap, separate budget).
  Already run.
- **`cleanup_shells.py`** — removes "empty shell" entries (games scraped while still
  unreleased, carrying no real data) from `games.json`, filing them back into
  `catalog["pending"]` so the waiting-room promotes them when they release. Free and
  released-but-thin games are kept.

Once their work is done and committed, the backfill scripts (and their one-off
workflows) can be deleted from the repo.

---

## 5. The seeds system

`seeds.txt` lets you push specific games to the **front** of the scrape queue without
waiting for the frontier to reach their appid.

**The design (important):** `seeds.txt` is a **human-only, read-only-to-the-scraper**
file — you edit it, the scraper never writes to it. This preserves one-writer-per-file
(the scraper writing to a file you also hand-edit would reintroduce the collision
class). The scraper's record of "which seeds are already handled" lives in
`catalog.json["seeds_ledger"]`, keyed by seed provenance.

**How it works each run (`reconcile_seeds`):**

1. Read every active line in `seeds.txt` (comments / blank lines skipped).
2. For any seed not already handled, resolve it to appid(s) and push to the front of
   the priority queue.
3. Record it in the ledger so it's not re-processed (no loops).

**Seed line formats** (`parse_seed_line` / `resolve_seed`):
- A bare **appid** (`2495100`).
- A **store URL** (parsed for the appid).
- A **search term** or search URL — resolved live against Steam search, re-resolved at
  most once per `SEED_RESOLVE_TTL` (24 h) so a term keeps catching new matches.
- A **`!force` prefix** — one-shot re-scrape of an already-stored game (latched via
  `forced_applied` so it doesn't loop).

**Forget policy:** removing a line from `seeds.txt` does **not** delete the scraped
game from `games.json` — it just drops the ledger entry. The game stays.

**Live injection mid-run:** the main loop is a mutable `deque`, and at each checkpoint
(~10 min) it fetches `origin:seeds.txt` via `git show` and splices any newly-discovered
priorities to the front of the live work queue (`inject_new_seeds`). So a seed added
mid-run is picked up at the next checkpoint (~10 min latency) rather than waiting for
the next cron (~6 h).

`seeds_log.txt` is an append-only audit trail of seed reconciliations (scraper-owned,
committed alongside `catalog.json`).

---

## 6. Sale countdowns & offline expiry

Steam's price API doesn't always expose a clean sale end-date, and even when
`prices.json` has one, sales end on a schedule the frontend should respect without
needing a fresh scrape.

- `price_and_sale.py` records `discount_end` (Unix timestamp) for on-sale games from
  `GetItems`, and prunes expired sales.
- The frontend shows a **live countdown** for active sales and flags ones ending soon.
- `expireSaleIfEnded` collapses any sale whose `discount_end` has passed **entirely
  offline**: it zeroes the discount, restores base price, drops QHPP-after to
  QHPP-full, and marks `_expired_sale` for display until the next reload. No scraping
  involved — so countdowns are always honest even between price refreshes.

---

## 7. The HLTB estimation system (deep dive)

This is the most involved subsystem, added to fix a systematic distortion in QHPP.

### The problem

HowLongToBeat exposes three completion times: **main**, **main+extras**, and
**completionist**. Many games only have 1 or 2 of them. The original code computed
`avg` as the mean of *whatever happened to be present* — so:

- A game with only a **main** time got `avg == main` → understated.
- A game with only a **completionist** time got `avg == completionist` → badly
  overstated (a long 100% time treated as a typical playthrough).

Since QHPP defaults to the `avg` metric, this skewed the value score for hundreds of
games.

### The fix

When 1 or 2 of the 3 times are missing, **estimate the missing ones from the typical
ratio between the three times**, then compute `avg` over the now-complete triple.

**The ratio** is the **median** across all games that have all three real values
(median, not mean, because grind-heavy completionist outliers drag the mean up and
over-inflate a typical game). At the time of writing, that ratio was:

```
main : extra : complete  =  1 : 1.39 : 2.19      (327 real triples)
```

The ratio is **live** — recomputed from the current corpus on each run, so it
self-corrects as more real triples accumulate — with **frozen median constants as a
cold-start fallback** until there are enough real triples (`MIN_TRIPLES_FOR_LIVE = 30`).

**Anchoring:** missing values are derived from whatever real value(s) exist (not just
main), routing through the nearest reliable neighbour (main↔extra and extra↔complete
are adjacent and more reliable than the main↔complete jump).

### The `raw` ground-truth model

Each `hltb.json` entry now looks like:

```json
{
  "main": 53.4, "extra": 94.8, "complete": 171.8,
  "avg": 106.7,
  "match": "Stardew Valley",
  "fetched_at": 1782817321,
  "raw": { "main": 53.4, "extra": 94.8, "complete": 171.8 },
  "est": ["extra"]
}
```

- **`raw`** holds *only* genuine HLTB values (or null). **Zeros are normalized to
  null** on the way in — a game can't be played in zero hours, so a 0 is treated as
  "no value" and gets estimated like a missing one.
- Top-level `main`/`extra`/`complete` are the **effective** values: real where `raw`
  has them, estimated otherwise. These are what the frontend shows and QHPP uses.
- **`est`** lists which top-level fields are estimated (drives the frontend's distinct
  styling). Absent when nothing is estimated.
- **`fetched_at`** records when HLTB was last fetched (groundwork for future
  re-scraping by staleness — see §8).

**Why `raw` matters:** estimates are *always* derived from `raw`, never from prior
estimates. This guarantees (a) estimate quality only improves and never compounds
error, and (b) a future real re-scrape can losslessly overwrite into `raw` and
recompute, because the ground truth was never overwritten by a guess.

### The anti-pollution guard

The single most important correctness property: **only real `raw` triples feed the
ratio computation.** Without this, a backfilled entry — whose three values are now all
positive numbers — would masquerade as a real triple, the ratio would train on its own
estimates, and it would drift every run. `compute_ratios` reads from `raw` (which never
holds estimates), so this can't happen. This was caught and fixed during development by
a round-trip test: fill the whole corpus, recompute the ratio, and assert it's
byte-identical (327 → 327 real triples, unchanged).

### Frontend rendering

Estimated values render in a **distinct blue accent with a dotted underline** and a
hover tooltip: *"Estimated from the genre-average ratio between main / extras /
completionist times — not reported by HowLongToBeat. Replaced automatically if HLTB
data is found later."* When an estimated column is *also* the selected QHPP metric,
gold (selection) wins for the number but the dotted underline stays so it still reads
as estimated. A null value is never marked estimated even if its key is in `est`.

### The one-time backfill

`hltb_backfill.py` swept the existing `hltb.json` once to apply all of the above to
games already in the file (the live refresher fixes new games at the source). It:
adds `raw`/`est`/`fetched_at`, fills missing/zero values, corrects `avg`. It's
**idempotent** (estimates derive from `raw`, so re-running is a no-op) and was run via
the `backfill-hltb.yml` one-off workflow, which shares the `steam-hltb` concurrency
group so it can never write `hltb.json` at the same time as the refresher.

Result of the run: **387 entries received estimates, 347 skewed averages corrected,
7,600 genuine no-match blanks left untouched, 327 full-real entries untouched.**

---

## 8. GitHub Actions / workflows

All workflows live in `.github/workflows/`. Each is `workflow_dispatch` (manual) +
`schedule` (cron). All use **`actions/checkout@v5`** and **`actions/setup-python@v6`**
(both Node 24-based — bumped off the deprecated Node 20). v5/v6 specifically, rather
than the newest checkout v6/v7, because v5 keeps the credential-persistence behavior
the commit-and-push flow relies on without requiring a newer runner.

| Workflow            | Job             | Cron (UTC)             | Concurrency group | Runs                  |
|---------------------|-----------------|------------------------|-------------------|-----------------------|
| `scrape.yml`        | main scraper    | `0 0,6,12,18 * * *`    | `steam-scrape`    | `scraper.py`          |
| `prices.yml`        | pricing         | `7 */3 * * *` (3 h)    | *(own)*           | `price_and_sale.py`   |
| `hltb.yml`          | HLTB            | `53 */2 * * *` (2 h)   | `steam-hltb`      | `hltb_refresh.py`     |
| `tags.yml`          | tags            | `29 */2 * * *` (2 h)   | *(own)*           | `tags_refresh.py`     |
| `recent.yml`        | recent reviews  | `41 4,10,16,22 * * *`  | *(own)*           | `recent_refresh.py`   |
| `backfill.yml`      | last_update one-off | manual only        | `steam-scrape`    | `backfill_updates.py` |
| `backfill-hltb.yml` | HLTB est one-off    | manual only        | `steam-hltb`      | `hltb_backfill.py`    |

**Cron times are deliberately staggered** (`:07`, `:29`, `:41`, `:53`) so jobs don't
all fire at once. The two HLTB jobs share `steam-hltb` and the two catalog jobs share
`steam-scrape` (with `cancel-in-progress: false`) so members of a group **queue rather
than overlap** — protecting the file each group writes. Jobs in different groups (and
the ones writing distinct files) run freely in parallel, which is safe precisely
because of one-writer-per-file.

**Commit pattern (every job):** `git add <its-file>` → if staged changes exist →
commit → `git fetch origin main` → `git rebase --autostash origin/main` → `git push
origin HEAD:main`, with retry/backoff against concurrent pushes. Because each job only
touches its own file, the rebase always applies cleanly.

**Permissions:** every workflow needs `contents: write` to commit. Repo-level: Settings
→ Actions → General → Workflow permissions → **Read and write**.

> **Keep-alive note:** GitHub disables scheduled workflows after 60 days of repo
> inactivity. The frequent committing jobs keep the repo active, so this never trips
> as long as scraping is running.

---

## 9. Data file schemas (quick reference)

All files share a `{ generated_at, count, <payload> }` envelope. Live counts below are
approximate snapshots and grow over time.

**`games.json`** — `{ generated_at, count, games: [ ... ] }`, ~17.7k games. Each record:
```json
{
  "appid": 10, "title": "Counter-Strike",
  "url": "https://store.steampowered.com/app/10",
  "rating_pct": 97, "review_count": 260284,
  "price_initial": 9.99, "price_final": 1.99, "discount_pct": 80,
  "is_free": false,
  "release_date": "Nov 1, 2000", "release_ts": 973036800,
  "tags": ["Action"],                       // genre fallback; tags.json overrides
  "last_update_ts": 1739968505,
  "scraped_at": 1782749345
}
```

**`prices.json`** — `{ generated_at, country, count, prices: { appid: {...} } }`:
```json
{ "10": { "price_initial": 9.99, "price_final": 1.99, "discount_pct": 80,
          "discount_end": 1783616400, "scraped_at": 1782809229 } }
```

**`hltb.json`** — `{ generated_at, count, hltb: { appid: {...} } }`: see §7 for the
full shape (`raw`/`est`/`fetched_at`).

**`tags.json`** — `{ generated_at, count, tags: { appid: [tag, ...] } }`:
```json
{ "10": ["Action","FPS","Multiplayer","Shooter","Classic","Team-Based","First-Person","Competitive"] }
```

**`recent.json`** — `{ generated_at, window_days, count, recent: { appid: {...} } }`:
```json
{ "4834070": { "recent_pct": null, "recent_count": 0, "recent_scraped_at": 1782661984 } }
```

**`catalog.json`** — scraper state (not merged by the frontend):
```json
{
  "cursor": 1000,
  "pending":  { "385250": null },           // appid -> release_ts|null (waiting room)
  "skipped":  [206450, 208570],             // non-game / no-store-page appids
  "priority": [],                           // resolved seed queue
  "seeds_ledger": { "id:2495100": { "kind": "id", "resolved_ts": 1782806146,
                                    "ids": [2495100], "forced_applied": false } },
  "force_refresh": [],
  "last_sync": 1782763772
}
```

**`sales.json`** — legacy standalone sale-end file (`{ appid: { discount_end,
scraped_at } }`), superseded by `prices.json`'s `discount_end`.

---

## 10. Operating the system

### Normal operation

Nothing needed — the cron schedules keep all six data layers fresh and the site
updates as commits land. Coverage of new games grows run to run as the scraper's
frontier advances.

### Setup from scratch

1. Push all files to a **public** repo (keep `.github/workflows/` structure).
2. Settings → Actions → General → Workflow permissions → **Read and write**.
3. Add the `STEAM_API_KEY` secret (free from
   https://steamcommunity.com/dev/apikey) — recommended; without it the scraper falls
   back to the keyless app list (more non-games, no change-detection).
4. Settings → Pages → deploy from branch `main`, folder `/root`.
5. (Optional) seed games to scrape first in `seeds.txt`.
6. Actions tab → run each workflow once to kick things off; they then run on schedule.

### Running locally

```bash
pip install -r requirements.txt
STEAM_API_KEY=... RUN_MINUTES=30 python scraper.py
```

Git commits are skipped when not running inside Actions (`GITHUB_ACTIONS` unset).
Open `index.html` directly to view (it shows sample data until a real `games.json`
exists alongside it).

### Editing workflow: all repo changes via GitHub web UI

This project is maintained by uploading files through the GitHub web UI (no local git
clone for edits). When making programmatic changes, the working pattern is: clone to a
scratch dir, edit/test there, then upload the final files through the web UI. **Caution:
a manual upload of a data file can clobber an Action that's mid-write to it** — pause
the relevant workflow (or rely on a one-off workflow that regenerates the file on the
runner) rather than hand-uploading large data files that a job owns. This is exactly
why the HLTB backfill ran as a *workflow* rather than a hand-uploaded `hltb.json`.

---

## 11. Performance notes & hard-won lessons

These are real findings from building the system, recorded so they aren't
re-discovered the hard way:

- **Measure scraper pace between checkpoint-commit timestamps, never from visible log
  lines.** Eyeballing log output across a short window once produced a false "1.5
  games/min" panic reading — it was a measurement artifact from a checkpoint-commit
  pause, not the real rate (~11/min measured properly).

- **The decoupling was the big win.** Pulling HLTB, SteamSpy, and prices out of the
  main loop took it from ~6 games/min to ~13+ games/min, because each of those was a
  multi-second per-game blocking call. The general principle: the slow scrape should
  only do the fast, always-changing catalog work; static/flaky enrichment belongs in
  separate out-of-band jobs.

- **Independent endpoints don't compete for budget.** HLTB hits howlongtobeat.com,
  tags hit steamspy.com — neither touches the Steam storefront's ~200/5min limit, so
  they can run near-continuously in parallel without slowing the scraper.

- **Coverage gaps are mostly by design, not bugs.** Prices intentionally excludes
  free/unpriced games; recent is a ranked subset by design. Only HLTB and tags are
  genuine throughput bottlenecks (single-threaded, one-time-per-game), which is why
  their crons run every 2 h with tuned delays.

- **Steam 403 cooldowns are rare enough to ignore.** They occur roughly once per
  11,000+ games at the current delays — no special handling warranted; the flat
  cooldown-and-retry suffices.

- **One-writer-per-file is load-bearing.** Almost every "why is this structured this
  way" answer traces back to it. The git push-collision class that plagued early
  development disappeared entirely once each job owned a disjoint file.

---

## 12. Known caveats

- **HLTB matching is by title similarity** (`HLTB_MIN_SIMILARITY = 0.65`), so
  obscure or oddly-named games may not match (shown as `—`). A genuine no-match is
  recorded so it isn't re-searched forever; a future re-scrape pass (§8) can retry
  these.
- **Tags fall back to Steam genres** when SteamSpy has nothing for a game, so the tag
  column is never empty but may be coarser for some titles.
- **Estimated HLTB values are estimates**, clearly marked (blue + tooltip). They're a
  reasonable stand-in for the `avg`/QHPP, not ground truth, and are replaced the
  moment real HLTB data is found.
- **Dataset size:** the single-`games.json` approach is fine into the tens of
  thousands of games. Far beyond that, consider sharding `games.json` and loading
  shards on demand.

---

## 13. Future work (deferred by design)

- **HLTB re-scraping.** Currently the HLTB job only fetches games it has *never*
  touched — it finishes one full pass over the whole catalog before any re-scraping.
  Once that pass is complete, a re-scrape job will retry in priority order:
  **(1) partial entries** (≥1 real value — likely more data exists now),
  **(2) blank entries** (no match first time — retry for newly-added HLTB titles),
  **(3) full-real entries** (re-check for changes only — lowest yield). The
  `fetched_at` stamp added in §7 is the groundwork: it lets that job order by staleness
  within each bucket. The overwrite-into-`raw` logic the data model already supports
  makes this clean — real values overwrite, estimates recompute, blank re-fetches
  don't wipe existing data.

- **Cleanup of one-off scripts.** `hltb_backfill.py` + `backfill-hltb.yml` and
  `backfill_updates.py` + `backfill.yml` have done their jobs and can be removed from
  the repo whenever convenient. `hltb_estimate.py` stays — the live refresher imports
  it permanently.

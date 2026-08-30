# Review Digest — design memo

**Status: Phase 0 run (§14) · Phase 0.5 Worker written, awaiting deploy. Phase 1 next.** Design record for a per-game, on-demand pull of
*real Steam review text*, packaged into one copy-paste block with an AI prompt attached, so
the user gets a quantitative issue breakdown from actual players instead of reading 500
reviews by hand.

All design questions are **decided** (§12); the empirical ones were answered by the Phase 0
probe on 2026-08-28 (**§14 — read this first**, it changes §3, §5 and §6).

**Later than the phases below:** §16 and §17 record what shipped on 2026-08-30 — precomputed
topic signals and the NOW-window fix (§16), then the whole deferred output redesign (§17).
§15 holds the specs §17 was built against and is kept as written, not updated to match.

Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md) (§1 design principles, §3.1 the
review-TEXT roadmap item this is adjacent to, §12 the Worker) · [ROADMAP.md](ROADMAP.md).

---

## 1. The flow

```
1. find a game            → existing search / filters, no change
2. hit the reviews entry  → grid card button, or the review count in the table row
3. QTPD fetches 500 real reviews from Steam, live, in the browser
4. QTPD compacts them into one text block, AI prompt on top
5. Copy / Download .txt   → paste into any AI → quantitative answer
```

The benefit is step 3–4: **capture of most/all recent reviews stops being a manual
process.** QTPD does not summarize — it does the *collection and packaging*, which is the
part that is tedious, mechanical, and currently impossible by hand.

---

## 2. Why on-demand, and not a scraped data layer

ARCHITECTURE §3.1 already did this arithmetic for the keyword-extraction item: raw review
prose for ~1000 reviews × ~78k games is **1 GB+**, and `playtime_raw/` is *already* sharded
across 64 files because it hit GitHub's 100 MB/file cap. Storing review text in the repo is
not on the table.

On-demand fetch dodges the whole problem: **nothing is stored.** It also gets freshness for
free — the reviews are as of the moment the button was pressed, which for "is this game
fixed yet" is the entire question.

**This is not the ROADMAP §3.1 item.** That one is *aggregate keyword counts for every
game*, scraped during the existing playtime walk, surfaced as a column. This one is
*per-game, full-fidelity, on request*. They are complementary and should not be merged:

| | §3.1 keyword layer | this (Review Digest) |
|---|---|---|
| coverage | all ~78k games | one game, on click |
| fidelity | counts from a fixed lexicon | the actual prose |
| freshness | last playtime sweep | live |
| cost | free (rides an existing walk) | ~5 requests per click |
| storage | one small JSON | none |

§3.1 explicitly parked its Option **C** ("LLM one-line summary per game") because it "adds
an external-model dependency + cost + batch job, breaking the runs-entirely-free model."
The Review Digest gets C's payoff **without** that dependency: it exports the prompt and
lets the user's own AI do the inference. No model, no key, no cost, no batch job.

---

## 3. ~~THE BLOCKING UNKNOWN~~ — ANSWERED: no CORS. Branch A1.

> **Probe result (2026-08-28): `appreviews` returns NO `Access-Control-Allow-Origin`.**
> Status 200, full JSON, but no CORS header — and the OPTIONS preflight returns nothing
> either. ARCHITECTURE §1 holds for this endpoint too. **A Cloudflare Worker passthrough
> is required.** The rest of this section is the reasoning that led there.

ARCHITECTURE §1 states flatly: *"Steam sends no CORS headers, so the browser cannot call
Steam directly."* That was established for the **storefront/wishlist** endpoints. It has
**not** been verified for `store.steampowered.com/appreviews/`, which is a different
endpoint, and the answer decides whether this feature needs a backend at all:

- **Branch A0 — CORS present.** Zero backend. The whole feature is client-side in
  `index.html`. No new job, no new data file, no Worker, nothing to deploy or keep alive.
- **Branch A1 — no CORS.** A Cloudflare Worker passthrough (~40 lines) forwarding
  `/?reviews=<appid>&cursor=…` to Steam and re-serving it with
  `Access-Control-Allow-Origin`. Same pattern as the wishlist proxy (§12) — but that
  Worker's source is **not in this repo and appears to be lost**, so A1 realistically means
  writing a new one.

**The probe cannot run from a dev sandbox** — `store.steampowered.com` is blocked there
(verified 2026-08: proxy returns 403 to CONNECT). Same wall the trailer work hit, resolved
there with a runner-side dump mode (`QTPD_DUMP_TRAILERS=1`). Do the same here.

**This does not block starting.** The UI, compaction, format and prompt are identical in
both branches, behind one seam:

```js
async function fetchReviewPage(appid, params, cursor) { … }   // A0: Steam. A1: Worker.
```

---

## 4. What Steam actually gives us

`GET https://store.steampowered.com/appreviews/<appid>?json=1` — public, **keyless**,
already called by three jobs in this repo (`scraper.py:506`, `playtime_refresh.py:531`,
`recent_refresh.py`).

| param | values | note |
|---|---|---|
| `filter` | `recent` / `updated` / `all` | `recent` paginates deep and reliably; `all` is helpfulness-ranked and unstable past a few cursor pages — **verify in the probe** |
| `language` | `english` / `all` | §5 |
| `review_type` | `all` / `positive` / `negative` | reserved for a possible Balanced mode |
| `purchase_type` | `all` / `steam` / `non_steam_purchase` | repo jobs use `all` |
| `num_per_page` | max **100** | hard cap → 500 = 5 requests |
| `cursor` | `*` then echo | must be URL-encoded |
| `filter_offtopic_activity` | `0` **includes** review bombs | we include — §5. Confirm the polarity in the probe |

**Per-review fields** (audited in ARCHITECTURE §3.1 — all of this is already fetched and
discarded on every playtime run): `recommendationid`, `review`, `voted_up`, `votes_up`,
`votes_funny`, `weighted_vote_score`, `comment_count`, `timestamp_created`,
`timestamp_updated`, `language`, `steam_purchase`, `received_for_free`,
`written_during_early_access`, `primarily_steam_deck`, and `author{ steamid,
num_games_owned, num_reviews, playtime_forever, playtime_at_review, last_played }`.

**`query_summary`** (first page, `cursor=*`): `total_reviews`, `total_positive`,
`total_negative`, `review_score_desc`. **The population anchor** that keeps the AI's
percentages honest (§5).

---

## 5. Sampling — decided

**Default: the 500 most recent reviews, `filter=recent`, English, review bombs included.**

**Size — 500.** 5 requests. ~125 KB raw ≈ **~31k tokens**, ~20–25k after compaction (§6).
Comfortable for Claude and most modern chat boxes; revisit if it proves too big in
practice.

**Mode — `recent`.** Answers "what is this game like *now*", which is the actual question,
and it is the filter that paginates reliably.

**Language — English by default, an *All languages* toggle in the modal.** English-only
gives clean signal and reliable counting; the toggle exists because on a
Chinese- or Russian-majority game, English-only is a genuinely misleading minority slice.
The header always prints the non-English share so the limitation is visible either way.

**Review bombs — INCLUDED (`filter_offtopic_activity=0`).** Deliberate. There is no such
thing as an illegitimate review here: if a publisher or developer did something people are
angry about, that *is* something a prospective buyer needs to see, and it will come out in
the analysis on its own. Suppressing it would be QTPD deciding which player anger counts.

**But the prompt must separate it, not blend it.** A coordinated campaign and a crash bug
are both real and both worth knowing — they are just not the same fact. So the prompt
requires the AI to:
1. detect a coordinated spike (publisher, DRM, price change, politics) and report it as its
   **own section** with its own count and date range, and
2. give the issue table **both ways — with and without those reviews**.

That way you see the campaign *and* the underlying game quality, and neither one hides the
other.

**Anchor coupling — RESOLVED (probe §14).** `query_summary` **does** respond to
`filter_offtopic_activity`, so the anchor is fetched with the *same* setting as the sample
and there is exactly one consistent number. No dual-anchor needed. It also responds to
`language`, so an English sample gets an English anchor — which is the correct comparison.

**Honesty rules that make the numbers mean something:**
1. `query_summary` is always printed — the true all-time split is at the top, fetched with
   the same `language` and `filter_offtopic_activity` as the sample.
2. The sampling mode is stated verbatim in the header.
3. The prompt must report counts as "N of the 500 sampled", never as a bare percentage of
   the game.

---

## 6. Compaction — the token problem

Measured, not guessed — every number below comes from the Phase 0 run (§14).

| pass | what | measured effect (§14) |
|---|---|---|
| **Per-review cap** | 600 chars + ellipsis | truncates only **6.1%** of reviews, saves **~35%** of the budget (20.9k → 13.7k tokens). The best lever by far — **keep 600** |
| **Near-duplicate drop** | hash of lowercased alphanumerics | 4 groups, **32 removable copies** in 1793 (1.8%). Small on tokens, but the worst offender was posted **30×** — exactly the skew this exists to stop |
| **ASCII/emoji-art drop** | non-alnum ratio > 0.4 on >80 chars | drops **2.1%** of long reviews. The distribution is **bimodal** (p50 0.034, p99 0.993), so *any* threshold from 0.30–0.60 gives the same answer — **0.4 confirmed, and it is not a sensitive knob** |
| **BBCode strip** | whitelisted tags only | **0.5%** of reviews contain markup. Near-worthless as a token saver — **keep it for cleanliness, not budget**. Must whitelist real tags: the probe's first regex matched `[sailing]` and `[russians]` in prose, and stripping those would delete words out of a review |
| **Whitespace collapse** | newlines → space, runs → one | cheap, keeps the one-review-per-line format intact |
| **Min length** | keep everything ≥1 char | see below — do **not** drop short reviews |

**The headline measurement: the median Steam review is 35 characters.** Not the ~250 the
plan assumed. The distribution is p25 **10** · p50 **35** · p75 **115** · p90 **377** ·
p99 **2081** · max **7953**.

**Budget at 500 reviews** (scaled from the probe's 1793):

| cap | tokens | truncated |
|---|---|---|
| none | ~20.9k | 0% |
| 800 | ~15.0k | 4.5% |
| **600** | **~13.7k** | **6.1%** |
| 400 | ~11.7k | 9.5% |
| 300 | ~10.4k | 12.2% |

Even **uncapped, 500 reviews is only ~21k tokens** — comfortably pasteable anywhere. The
600 cap is kept because a single 7,953-char essay is ~2,000 tokens of one person's opinion
and distorts the tally, not because the budget demands it.

**38% of reviews are under 20 characters** ("good", "gg", "+rep", "10/10"); 6.2% are under
4. This does *not* become a filter. Short reviews are real sentiment, they cost ~2 tokens
each, and dropping them would bias the sample **negative** — one-word reviews skew positive.
Filtering them would also be QTPD deciding which reviews count, which is the same thing we
refused to do with review bombs (§5).

Instead the header **reports** it: `substantive: 310 of 500 have >20 chars of text`. The AI
is told the issue counts can only come from those, while the ▲/▼ tally legitimately uses all
500. Same principle as everywhere else here — do not hide the shape of the sample, state it.

**Every drop is counted and printed in the header.** The bundle never hides what it did to
the sample.

---

## 7. Output format

One review per line — JSON would roughly double the token count on braces, quotes and
repeated keys and buys nothing.

```
=== QTPD REVIEW DIGEST ===
You are given real Steam reviews for one game. Instructions are at the BOTTOM.

GAME: Cyberpunk 2077  (appid 1091500)
ALL-TIME: Very Positive — 79% of 723,411 reviews  (571,494 ▲ / 151,917 ▼)
LAST 30 DAYS: 88% of 4,210
SAMPLE: 500 newest English reviews (filter=recent) · fetched 2026-08-28
  sample split: 402 ▲ / 98 ▼  (80% positive)
  off-topic/campaign reviews: INCLUDED
  excluded: 21 ASCII-art · 9 duplicates · 78 truncated at 600 chars
  language: english only (≈38% of this game's reviews are other languages)
LEGEND: ▲/▼ recommends · Nh hours at review · date · ↑N helpful votes
        [EA] written during early access · [free] free/non-Steam copy
        [deck] played on Steam Deck · [upd] review edited after posting

--- REVIEWS (500) ---
▲ 142h 2026-08-27 ↑31 [upd] | Best it's ever been. Holds 90fps on a 3070 since 2.3 …
▼ 8h 2026-08-27 ↑4 | Crashes on every alt-tab with a DX12 device-removed error. Refunded.
▼ 61h 2026-08-26 ↑12 [deck] | Runs at 25fps docked, police AI still teleports …
▲ 340h 2026-08-26 ↑8 [EA][free] | Review key. Rough at launch, but the 2.0 rework …

--- INSTRUCTIONS ---
[loaded from review_prompt.md — see §8]
```

**Prompt at top and bottom.** A short framing line first (so the reader knows what they are
looking at), the full instructions last (so they are the most recent thing in context after
a long paste). Known reliability pattern for long pastes; costs ~200 tokens.

### The four flags — and the requirement they create

All four ship, at ~2–4 tokens per review. **All four are confirmed live and populated**
(§14) — none is dead weight. Each changes what a review *means*:

| flag | source field | why it matters |
|---|---|---|
| `[EA]` | `written_during_early_access` | an EA review complaining about missing content is a completely different fact from a post-1.0 one |
| `[free]` | `received_for_free` or `!steam_purchase` | review-key and gifted reviews skew positive |
| `[deck]` | `primarily_steam_deck` | Deck performance is its own technical category, currently blended into general perf |
| `[upd]` | `timestamp_updated != timestamp_created` | someone revisited their verdict after patches — direct evidence for the trend question |

**Measured hit rates over 1,800 live reviews:** `[EA]` 600 (all of Valheim — still in early
access, so the flag is doing exactly its job) · `[free]` 165 (6 `received_for_free` + 159
`!steam_purchase` — the *inverted purchase* half carries almost all the signal, which is why
`[free]` is defined as either) · `[deck]` 22 · `[upd]` 68.

**The flags are useless unless the prompt uses them.** `review_prompt.md` must explicitly
instruct the AI to classify and sort on them — separate EA-era complaints from current
ones, break technical issues out by Deck vs desktop, note whether `[free]` reviews skew the
sentiment, and lean on `[upd]` for the trend section. Flags in the data with no instruction
to read them is just wasted tokens.

---

## 8. The prompt lives in its own file

**`review_prompt.md`, at the repo root, fetched at modal-open time.** The prompt is the
part that will be iterated on hardest and longest, and it should not require touching a
5,500-line `index.html` to tune a sentence.

- **Not a 14th load-time fetch.** The site fetches 13 files at load (ARCHITECTURE §2); this
  one is **lazy** — requested only when the modal first opens, ~2 KB, then cached in memory
  for the session.
- **`cache: "no-store"`**, matching the wishlist fetch pattern (`index.html:4488`), so an
  edit is live on the next modal open rather than after a CDN cache expiry.
- **Inline fallback constant.** If the fetch fails, the bundle still gets a minimal built-in
  prompt. A digest must never be produced with no instructions attached.
- **Not a data-layer file.** No job writes it; it is authored by hand. ARCHITECTURE §1's
  one-writer rule is about jobs racing each other and is unaffected.
- Optionally a `<!-- v3 -->` first line, echoed into the bundle header, so an output can be
  traced back to the prompt that produced it.

The prompt content itself is deliberately **not frozen in this memo** — it gets its own
iteration cycle in that file. It must cover: verdict · issue table with counts · the
technical/design/content/monetization/service rollup · the headline technical share ·
campaign detection as a separate section with both tallies (§5) · trend from dates and
`[upd]` · flag-aware classification (§7) · praise · and the sample-vs-population caveat.

---

## 9. UI — where it lives in `index.html`

**Grid card.** `.gi-actions` on the details face — `index.html:3973`, next to the existing
`Steam ↗`. Add **`Reviews ⇩`**. Already-styled slot, works on phone.

**Table row — zero extra space.** The Game cell already prints the review count under the
title (`.gsub`, `index.html:2668` — *"1,015,944 reviews"*). **That text becomes the
button.** It costs no new pixels, it already says the word "reviews", and clicking a review
count to get the reviews needs no explaining. Underline on hover + pointer cursor + tooltip
carry the affordance; make it a real `<button>` for keyboard access. Games with no
`review_count` render `"app 570"` instead and are simply not clickable. It sits *outside*
the `<a class="gtitle">` store link, so there is no nested-interactive problem.

**Modal.** New `#revModal`, reusing the `.pop-host` / `.pop-backdrop` styling at
`index.html:1907` — but **not** `#popover` itself, which is the small filter/CSV editor and
is the wrong size and lifecycle.

- **Controls:** language (English / All) · size · **Fetch**.
- **Progress:** `page 3/5 · 287 reviews · ~19k tokens`, live. Five sequential requests is
  2–4 s and silence reads as broken.
- **Result:** readonly `<textarea>` preview + **Copy all** + **Download .txt** (reuse the
  Blob pattern at `index.html:4366`) + live char/token estimate.
- **Abort:** `AbortController`; closing the modal cancels in flight.
- **Cache:** last few bundles in memory / `sessionStorage`, so re-opening is instant.
- **Failure:** the existing `toast()` at `index.html:4417`, same voice as the wishlist
  failure path.

---

## 10. Risks and answers

| risk | answer |
|---|---|
| **Steam rate-limits the browser** (A0) | 5 requests is far under the ~200/5min budget; 250–400 ms between pages, disable Fetch while one runs |
| **Worker IP shared across users** (A1) | Cloudflare Cache API keyed on appid+params, 30–60 min TTL — Steam's numbers barely move in an hour, and repeat opens become free |
| **The scrapers' own budget** | Untouched under A0 (the fetch comes from the *user's* IP). Under A1 it is the Worker's IP pool, still separate from the runners already sitting at `STEAM_DELAY = 1.5` |
| **`filter=all` cursor unreliable past a few pages** | Everything is built on `filter=recent`; confirm the depth limit in the probe |
| **Non-English noise** | English default, All as a toggle, non-English share always printed |
| **ToS** | Public, keyless, documented endpoint the repo already calls in three jobs; output is a user-initiated copy for personal use; **no prose cached in the repo** — which is also the storage answer from §2 |

---

## 11. Phases

**Phase 0 — probe. ✅ DONE — run 2026-08-28, findings in §14.** `review_probe.py` +
`.github/workflows/review-probe.yml` (`workflow_dispatch` only, never scheduled),
runner-side because the sandbox is blocked.

**To run it:** Actions → *0.1 Review Digest probe* → **Run workflow**. Optional inputs
`appids` (comma-separated) and `pages`. Read the findings in the run log; download
`review-probe-findings` from the run's Artifacts for `report.json` and the raw
`sample.json`.

It answers, in one ~5-minute run:

| # | question | what it decides |
|---|---|---|
| **Q1** | does `appreviews` send `Access-Control-Allow-Origin`? | **A0 (no backend at all) vs A1 (write a Worker)** |
| **Q2** | how deep does the `recent` cursor page cleanly? | whether a 500-review sample is even reachable |
| **Q3** | is `filter_offtopic_activity=0` really *include*, and does `query_summary` move with it? | whether the header prints one anchor or two (§5) |
| **Q4** | are the four flag fields present *and* populated? | whether any of `[EA]` `[free]` `[deck]` `[upd]` is dead weight |
| **Q5** | real length / art-ratio / BBCode / duplicate distributions | replaces the placeholder 600-char cap and 0.4 art ratio with measured numbers (§6) |

It also reports the **English share** per game, which is the evidence for how misleading
the English-only default is on a given title.

**It commits nothing.** Findings go to the run log, the raw sample goes out as a build
artifact — the no-prose-in-the-repo rule (§2) applies to the probe too. `permissions:
contents: read`, so it *cannot* write even by accident.

**Phase 0.5 — the Worker. ✅ WRITTEN (`worker/`), awaiting deploy.** The probe put us on
branch A1, so the browser cannot reach Steam and this had to exist before any of the UI
could be tested against real data. Deploy steps are in
[`worker/README.md`](worker/README.md); until it is deployed and `REVIEWS_PROXY` points at
it, Phase 1 has nothing to fetch from. What it does:

- One route: `/?appid=<n>&cursor=<c>&…` → `store.steampowered.com/appreviews/<appid>`.
- **Param allowlist and a numeric-appid check.** Without them this is an open proxy for
  anything on Steam's domain — it must forward only the handful of params in §4.
- CORS headers scoped to the Pages origin, not `*`.
- Cloudflare **Cache API**, 30–60 min TTL keyed on the full param set. Steam's numbers
  barely move in an hour and this makes repeat opens free.
- **Its source lives in this repo this time** (`worker/`). The wishlist Worker's source was
  lost, which is the entire reason A1 is expensive today; do not repeat that.
- `num_per_page=0` is preserved rather than clamped — it means *summary only, no bodies*,
  which is how the bundle header fetches its population anchor in one cheap call. An early
  `|| 100` fallback silently turned that into a full page fetch; caught by `worker/test.mjs`.
- Unit tests (`node worker/test.mjs`) cover the appid validation, the param allowlist, the
  clamping and the CORS allowlist — pure functions, no Cloudflare runtime needed.

**Phase 1 — MVP.** `fetchReviewPage` (pointed at the Worker) + compaction + formatter +
`review_prompt.md` loader + modal + copy + download. Recent / 500 / English, bombs in, all
four flags, substantive-count in the header. Both entry points (grid card + table review
count) — the table one is a one-line change, no reason to defer it.

**Phase 2.** Language toggle, size picker, session cache, prompt iteration against real
games.

**Decided against — the in-browser lexicon counter.** A JS keyword count of
technical-vs-design issues was considered and **dropped**. A hardcoded word list cannot
handle negation ("zero crashes, runs great" scores as a crash complaint), sarcasm, or
unlisted synonyms, so it would systematically undercount — and it would sit next to the
AI's answer as a second, worse verdict with no way to tell which is wrong when they
disagree. The AI doing this properly *is* the feature.

**…reversed on 2026-08-30. See §16.** The objection above is about a lexicon count in the
**output**, and it still stands — nothing keyword-derived is ever printed as a verdict. What
shipped is a lexicon count in the **input**: a `TOPIC SIGNALS` block inside the bundle, read
by the model and thrown away. It never reaches the reader, so there is no second verdict to
disagree with, and negation and synonyms are the model's job to correct rather than the
regex's job to get right. What forced the reversal was measurement: three models given the
same 500 reviews returned counts differing by up to 3.4x for the same issue, while every
number they merely *copied* from TIMELINE was identical in all three.

---

## 12. Decisions — all closed

| # | decision | choice |
|---|---|---|
| 1 | sample size | **500** most recent (revisit if it proves too big) |
| 2 | sample mode | **recent** |
| 3 | prompt placement | **inline in the bundle**, top + bottom |
| 4 | review bombs | **included** — a publisher screw-up is legitimate signal; prompt reports it separately and gives both tallies |
| 5 | in-browser lexicon count | **dropped as output; reversed as input 2026-08-30** — precomputed into the bundle for the model to check itself against, never printed (§16) |
| 6 | language | **English default, All as a toggle** |
| 7 | grid entry point | `.gi-actions`, next to `Steam ↗` |
| 8 | table entry point | **the review count in `.gsub` becomes the button** — zero extra space |
| 9 | prompt location | **`review_prompt.md`**, its own file, lazily fetched, iterated separately |
| 10 | per-review flags | **all four** — `[EA]` `[free]` `[deck]` `[upd]`, and the prompt must classify/sort on them |

## 13. Files touched

| file | change |
|---|---|
| `index.html` | one new ~400-line section: fetch, compact, format, modal; plus two small entry-point edits (`:2668`, `:3973`) |
| `review_prompt.md` | **new** — the prompt, iterated independently |
| `review_probe.py` + `.github/workflows/review-probe.yml` | **added** — Phase 0 diagnostic; read-only, commits nothing, manual trigger only |
| `worker/` | **added** — the A1 proxy (`index.js`, `wrangler.toml`, `README.md`, `test.mjs`). In-repo by design; the wishlist Worker's source was lost |
| `ARCHITECTURE.md` / `ROADMAP.md` | new section + cross-reference |

**No new data file, no new scheduled job, no change to any existing writer.**
ARCHITECTURE §1's one-writer-per-file rule is untouched and nothing here can interfere with
the scrapers.

---

## 14. Phase 0 findings — the live run

**Run:** [33168828313](https://github.com/MLMariss/SteamQTPD/actions/runs/33168828313) ·
2026-08-28 · Cyberpunk 2077 (1091500), Valheim (892970), Dota 2 (570) · 6 pages each ·
1,800 reviews · 55 s.

### Q1 — CORS: **no. Branch A1.**

`appreviews` returns 200 with full JSON and **no `Access-Control-Allow-Origin`** (the
OPTIONS preflight carries nothing either). ARCHITECTURE §1's claim holds for this endpoint
too. **A Cloudflare Worker passthrough is required** — this is the expensive answer, and it
adds Phase 0.5 (§11).

### Q2 — cursor depth: **no constraint whatsoever.**

All three games: **6/6 clean pages, 600 unique reviews, zero duplicates, cursor advanced
every time.** 500 is reachable with room to spare; the ceiling was never tested because
nothing pushed back. If 500 ever proves too small, more is simply available.

### Q3 — off-topic flag: **`query_summary` IS coupled.**

Cyberpunk: `include` 983,491 vs `exclude` 975,799 — **7,692 off-topic reviews, and the
summary moved.** Valheim and Dota 2 were identical only because neither game has any
off-topic reviews at all.

So the anchor is fetched with the same `filter_offtopic_activity` as the sample and there is
**one consistent number** — the two-anchor fallback §5 was braced for is not needed.

`query_summary` also tracks `language`: Cyberpunk is 983,491 reviews overall but 417,281 in
English. An English sample therefore gets an English anchor, which is the correct comparison
rather than a bug.

*Still unproven:* the **polarity** of `filter_offtopic_activity`. No game in the set had
off-topic reviews inside its newest 100, so "0 = include" is inferred from the totals, not
demonstrated per-review. Re-run against a game with an **active** bomb to close it. Low
risk — the totals only make sense one way — but it is inference, not observation.

### Q4 — flags: **all four alive.**

| flag | true | of 1,800 |
|---|---|---|
| `[EA]` | 600 | exactly Valheim's whole block — it is still in early access, so the flag is behaving |
| `[free]` | 165 | 6 `received_for_free` + 159 `!steam_purchase` — **the inverted-purchase half carries the signal**, so `[free]` must be defined as either |
| `[deck]` | 22 | rare but real |
| `[upd]` | 68 | real |

`received_for_free` alone (0.3%) would have been near-dead weight. Defining `[free]` as
`received_for_free OR !steam_purchase` is what makes it worth its tokens.

### Q5 — compaction: **the assumptions were wrong in useful ways.**

1. **The median review is 35 characters**, not ~250. Steam reviews are dominated by
   one-liners.
2. **500 reviews is only ~21k tokens uncapped.** The budget was never the problem.
3. **BBCode is 0.5% of reviews.** It was assumed to be everywhere. It is not a token lever.
4. **The art-ratio threshold is not a sensitive knob** — the distribution is bimodal
   (p50 0.034, p99 0.993), so anything from 0.30 to 0.60 drops the same ~2%.
5. **38% of reviews are under 20 characters.** The single most consequential finding for
   the prompt (§6).

### Bugs the live data exposed in the probe itself

- **BBCode regex matched any `[word]`.** The run reported `[sailing]×1` and `[russians]×1` —
  people writing brackets in prose, not markup. A strip pass built on that regex would have
  silently deleted words out of reviews. Now whitelisted to real tags.
- **Q3's verdict conflated "no off-topic reviews" with "not coupled".** Valheim and Dota 2
  were reported as "query_summary does NOT move" when the truth is they had nothing to
  exclude. That false negative would have sent the design down the two-anchor path for no
  reason. The verdict now distinguishes the two cases.

Both fixed. They are worth recording because both were reasoning errors that only real data
could catch — the same lesson ARCHITECTURE §2.1 recorded from the trailers: *dump first,
then tighten*.

---

## 15. Planned upgrades — output redesign (ALL FOUR SHIPPED — see §17)

Specs only, no rationale. Sourced from the three-model comparison on 2026-08-30 (Claude, GPT
and Gemini against one Salt 2 bundle, plus a Gears Tactics bundle, appid 1184050). Items 1
and 2 of that review shipped as **§16**; **15.1–15.4 shipped 2026-08-30 as §17**, which
records what was built, the two places the spec was read against a rule rather than
literally, and how it was verified. The specs below are left as written — they are the
contract §17 was measured against, not a running description of the code.

### 15.1 Output restructure

`review_prompt.md` only. No code change.

**Section order** — first screen is the answer, the rest is evidence:

1. `INTEGRITY`
2. `### Snapshot`
3. `### Who it's for` — new
4. `### Loved vs hated` — new
5. `### Where the complaints land` — new
6. `### Notes`
7. `### Issues` — the existing detail table, moved last

**Snapshot**
- Header row becomes `| Field | Value |`. The current `| | |` is an empty header row; strict
  markdown renderers drop the whole table (observed in Gemini, which rendered every digest
  table as raw pipes).
- New row: `| Dragging the score | <top issue> — <N>% of all ▼ reviews, <rising / flat / falling> vs before |`.

**`### Who it's for`** — two bullet lists, max 4 bullets each:

```
**Buy it if you** — <trait>; <trait>; …
**Skip it if you** — <trait>; <trait>; …
```

Rule: every `Skip it if` clause traces to an Issues row that cleared the floor, or to a
TOPIC SIGNALS family with hits. No clause may be inferred from the genre.

**`### Loved vs hated`** — one table, max 5 rows, columns ranked independently. Replaces the
standalone Praise table.

```
| # | Loved | N | Hated | N |
```

**`### Where the complaints land`** — bucket rollup, 5 fixed rows, counted at review level
(a review complaining about two Technical things counts once):

```
| Bucket | Reviews raising ≥1 | % subst |
```

**Issues table**
- `▼/▲` header becomes `Quit / stayed`, order pinned ▼ first (Gemini flipped it to ▲/▼).
- One legend line directly under the table: *"Quit / stayed — of the reviewers who raised
  this: how many refused to recommend / recommended anyway."*
- Blank line required before every table.

**Acceptance**: the same bundle through all three models produces the same section order,
and every `Skip it if` clause in all three traces to a table row.

### 15.2 Floor raise and headline row

`review_prompt.md` only.

- Row floor rises from 3 reviews to `max(5, 2% of substantive)`; everything under goes to the
  Other tally.
- **Headline row**: when one concrete complaint clears 8% of substantive, it gets a row whose
  `Category` is free text in players' own words, overriding the fixed taxonomy for that row
  only. Max one per report; sorts first regardless of `Now`.
  Reference case — Gears Tactics 1184050: the Xbox/Microsoft account requirement is ~12% of
  substantive and 30% of all ▼ reviews, but the fixed taxonomy splits it across
  *Always-online & DRM*, *Support & communication* and *Crashes & launch*, so it never
  surfaces as one thing.
- Notes must call out the Other tally when it is the largest row.

### 15.3 Sample-size selector

`index.html`. `RD.size` becomes state.

- Three options in the setup dialog beside the language toggle: **300 · 500 · 1000**, default
  500. Confirm ordering against the "default leftmost" rule before building.
- `rdCollect` already derives its page count from `RD.size`; the constant becomes
  `rdState.size`. Steam caps `num_per_page` at 100, so 1000 = 10 pages ≈ +2.5s at the current
  250ms inter-page delay. Worker needs no change — I/O-bound, nowhere near free-plan limits.
- Button label and the `Fetch <N> reviews` copy read from state. `RD.size` also appears in
  both entry-point `title=` attributes; both must follow.
- Dialog copy must say what 1000 buys: *history* on slow games, not accuracy.

**Blocked on**: §16. Unaided model counting degrades with length, so 1000 without the
precomputed signals is worse than 500.

### 15.4 Reader-focus toggles

`index.html` + `review_prompt.md`.

Checkbox row in the setup dialog. Each checked box appends one line to a
`--- READER FOCUS ---` block emitted immediately after `--- INSTRUCTIONS ---`.

| toggle | TOPIC SIGNALS family it maps to (§16) |
|---|---|
| Potato PC | Performance & FPS |
| Steam Deck / handheld | Steam Deck & handheld |
| Needs a third-party account | Third-party account & always-online |
| Microtransactions / DLC | Microtransactions & DLC |
| Co-op with friends | Multiplayer & servers |
| Short game / value | Length & content · Price & value |
| Political or ideological content | Political & ideological content |

Rules the block states to the model:

- Each focus gets a guaranteed Issues row **even below the floor**, including `0` — "nobody
  mentioned this" is a valid and useful answer.
- Each focus gets one line in `### Who it's for`.
- Counts only. No editorialising in either direction, on any focus.

**Blocked on**: §16 for the families, §15.1 for `### Who it's for`.

---

## 16. Shipped 2026-08-30 — precomputed signals and the window fix

Two changes, both aimed at the same measured problem: **the numbers this report copies are
right and the numbers it counts are not.** Three models given the identical 500-review bundle
returned 58 / 25 / 17 reviews for the same issue and 97 / 38 / 128 for the top praise row,
while every figure they copied from TIMELINE — NOW sentiment, the trend in points, the
`[free]` split — came back identical in all three.

### 16.1 The NOW window could swallow the sample — fixed

`rdWindows` widened the NOW window when the last 90 days held fewer than `RD_NOW_MIN`
reviews, but had no matching guard at the other end. On a game busy enough that 500 reviews
do not reach back 90 days, `calN === byTime.length`: NOW became the entire sample, `before`
came back empty, and TIMELINE printed **no BEFORE and no TREND line at all** — while the
prompt still asked the model for a trend in points. The model supplied one anyway.

Now the two cases are separate branches on `calN < RD_NOW_MIN`:

- **below** — widen to the newest `RD_NOW_MIN` (unchanged behaviour)
- **at or above** — cap NOW at `RD_NOW_MAX` (0.6) of the sample, guaranteeing a BEFORE side

They are exclusive on purpose. A single `min`/`max` chain lets the cap undo the widening on a
slow game, where NOW legitimately is most of the sample. Narrowing is disclosed on its own
line the way widening already was.

### 16.2 Coverage — how much real time the sample is

A review count says nothing about the span it covers, and the same 500 reviews are 25 months
of Gears Tactics (~20/month) and about two days of a hit. `-15 pts` means opposite things in
each, and nothing in the bundle distinguished them. Added:

- `COVERAGE:` sample span in days plus the rate — **per day** under `RD_THIN_SAMPLE_DAYS`
  (60), per month above it, because "~5073 reviews/month" extrapolated off three days is
  arithmetic nobody asked for.
- `SPANS  :` how many days NOW and BEFORE each cover.
- Warnings under `RD_THIN_SAMPLE_DAYS` (the sample carries no history) and under
  `RD_THIN_NOW_DAYS` = 14 (the trend is a same-fortnight read). Prompt rule 9 makes the model
  say so in the Snapshot rather than reporting a direction.

### 16.3 TOPIC MENTIONS — the lexicon count, reversed as an input

**This reverses §12 decision 5, and only halfway.** The original objection — a keyword tally
printed *next to* the model's answer is a second, worse verdict — still holds, and nothing
here is ever shown to a reader. What ships is a tally printed *inside* the bundle, which the
model reads, corrects against the text, and discards.

- 17 keyword families in `RD_TOPICS`. Each is a list of clauses; a clause may carry a `near`
  term that must also match, which is what makes "account" usable ("account" alone is
  meaningless, "account" plus "xbox" is decisive). Never add `/g` — the regexes are reused
  across every review and `/g` makes `.test()` stateful.
- Emitted as a pipe table: hits · now · before · ▼/▲ · helpful votes on the ▼ side · share of
  each window. Sorted like the Issues table so the model reads them in the same order.
- **A hit is a mention, not a complaint.** Praise matches too. Detecting complaints by regex
  is the negation problem that killed the original idea; the ▼/▲ column carries that
  distinction instead, read against `BASELINE ▼ RATE`.
- Families below 3 hits and at zero are named rather than dropped. "Nobody mentioned
  microtransactions" is a finding, and without the line the model cannot tell a family that
  was checked and found absent from one that was never looked for.
- Prompt rule 10: use it as a floor, explain in Notes any count that lands below half or
  above double the hits, and never reproduce the table. The block says the same about itself
  — a pipe table sitting in context is the most copy-pasteable thing in the bundle.

### 16.4 `[top]` — the reviews a buyer actually reads

The `RD_TOP_VOTED` (10) most-upvoted reviews are flagged on their own lines. A per-review
tally weights a drive-by one-liner the same as the review at the top of the store page, and
helpful votes are the only weight the sample carries.

Measured on Gears Tactics 1184050, 496 English reviews: **nine of the ten `[top]` reviews are
the Xbox account requirement, and all ten are ▼.** The same family carries 685 helpful votes
on its negative side and went from 8% of BEFORE to 16% of NOW. Nothing in the previous bundle
surfaced any of that, and no model counting by hand found it.

### 16.5 Verification

`test_review_digest.mjs` gains a third scenario (a 300-review sample across ~12 days) that
covers the narrowing branch, the per-day rate and both span warnings — the slow fixture only
ever exercised widening. The main fixture gains twelve topic-bearing reviews, three per
family across four families: without them every review matched nothing and the topic table
asserted a header with no rows under it.

Prompt is now **v6**: `[top]` in the line format, rule 9 (obey the coverage warnings, never
invent a missing TREND), rule 10 (TOPIC MENTIONS is a floor, not a source), a `Sample reach`
Snapshot row, and a Notes trigger for what the `[top]` reviews are about. The inline
`RD_PROMPT_FALLBACK` was updated in step — a stale fallback is the failure mode §8 already
recorded once.

**Not changed here**: the output skeleton. Restructuring it is §15.1–15.2 and is deliberately
separate, so the effect of the precomputed signals is visible against the current format
before the format moves under it.

---

## 17. Shipped 2026-08-30 — §15.1–15.4, the whole deferred set

Prompt is **v7**. All four specs went in together because 15.4 is blocked on 15.1 and
building the two prompt specs separately would have meant two rewrites of the same skeleton.

### 17.1 Output restructure (§15.1) and the floor raise (§15.2)

`review_prompt.md`, plus the inline `RD_PROMPT_FALLBACK` kept in step — §8's stale-fallback
failure mode, avoided the same way §16 avoided it.

Section order is now `INTEGRITY` · Snapshot · Who it's for · Loved vs hated · Where the
complaints land · Notes · **Issues last**. The Issues table is the working, not the finding,
and it spent five versions on the first screen because it was the first thing built.

Both spec'd tables landed as written: `| # | Loved | N | Hated | N |` with the columns ranked
independently, and the five-bucket rollup counted at review level. Snapshot gained the
`| Field | Value |` header and the `Dragging the score` row; the floor moved from a flat 3 to
`max(5, 2% of substantive)`; the `▼/▲` header became `Quit / stayed` with the order pinned and
a legend line under the table; every table now has a blank line before it.

Two things the spec did not say, decided here:

- **`Dragging the score` breaks rule 2's single-denominator rule** — it is a share of ▼
  reviews, not of substantive. Rule 2 now carries that as its one labelled exception, because
  an unexplained denominator switch in a file that forbids denominator switches is how a
  model decides the rule is soft.
- **The headline row's `Bucket` cell is not free text.** §15.2 frees the `Category`; leaving
  `Bucket` free too would put a sixth bucket in the rollup table and break its fixed five
  rows. The headline row keeps the bucket that fits best, and Notes says which others it drew
  from — which is the Gears Tactics finding stated rather than hidden.

### 17.2 Sample size (§15.3)

`RD.size` is gone; `rdState.size` replaces it, from `RD_SIZES = [500, 300, 1000]`.

**Order is 500 · 300 · 1000, not the spec's 300 · 500 · 1000.** §15.3 said to confirm against
the default-leftmost rule before building; the rule wins, and 500 leads.

Four places quote the number and all four now read state: the dialog copy, the fetch button,
and **both** entry-point `title=` attributes. The tooltips were the only hard part — the cards
are rendered long before the dialog opens, so `rdSyncEntryTitles()` reaches back and corrects
them on change. Without it the card promises 500 while the dialog fetches 1000.

Measured, on the ten-page fixture: 1000 reviews is 117 KB / ~29.8k tokens against 500's ~14k,
and 300 is ~12.2k. The dialog says what that buys — *history*, not accuracy — because on a
quiet game all three sizes cover the same years and the extra 15k tokens buy nothing.

### 17.3 Reader focus (§15.4)

`RD_FOCUS`, seven toggles, each mapping to the RD_TOPICS families that can answer it. Ticking
any emits a `--- READER FOCUS ---` block directly under the instructions — an amendment to the
task, not another input to weigh, which is why it sits there and not with the data.

The block restates all three rules in full even though prompt rule 11 carries them, because
the prompt is generic and only the block knows which focuses were asked for. The rule that
matters is the guaranteed row **at zero**: "nobody in 1000 reviews mentioned microtransactions"
is the answer the reader came for, and it is the one answer an unprompted report can never
give, because a bucket with no complaints simply does not appear in it.

Spec-vs-code naming: the spec's table says "TOPIC SIGNALS" and "Length & content"; the block
is called TOPIC MENTIONS (§16.3) and the family is `Length & amount of content`. Code uses the
real names — a focus pointing at a family that does not exist fails **silently**, which is why
the test asserts the mapping rather than trusting it.

Toggles are `.rd-opt` pills with `aria-pressed`, square-cornered to read as a multi-select
against the mutually-exclusive rows above them, rather than literal checkboxes.

### 17.4 Verification

`test_review_digest.mjs` gains 25 checks: the setup dialog's default-leftmost ordering, the
seven focus toggles and their `RD_FOCUS -> RD_TOPICS` mapping, the six output sections
asserted **by position** (§15.1's acceptance criterion is order, so order is what is pinned —
headings only, never prose, which is the mistake §16.5 already recorded), and a fourth
scenario that pages: 1000 reviews as ten cursor-chained requests, the four number sites moving
together, a focus toggled back off, and the block landing between INSTRUCTIONS and OVERVIEW.
It is the only scenario that pages — every other fixture returns an empty cursor and stops
after one page, so the loop the size selector consists of was previously never exercised.

**Not run here**: `node` is not installed on this machine, so the Playwright suite could not
be executed. Every one of the 25 assertions was instead run against a bundle built by the real
page in a browser — same page, same `rdBuildBundle`, same prompt file, with `fetch` stubbed to
serve ten pages — and all 25 pass. The Playwright wrapper around them is unexecuted code.

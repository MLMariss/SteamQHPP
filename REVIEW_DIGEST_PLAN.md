# Review Digest — design memo

**Status: Phase 0 RUN — all questions answered (§14). No feature code yet.** Design record for a per-game, on-demand pull of
*real Steam review text*, packaged into one copy-paste block with an AI prompt attached, so
the user gets a quantitative issue breakdown from actual players instead of reading 500
reviews by hand.

All design questions are **decided** (§12); the empirical ones were answered by the Phase 0
probe on 2026-08-28 (**§14 — read this first**, it changes §3, §5 and §6).

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

**Phase 0.5 — the Worker. NEW, and it gates Phase 1.** The probe put us on branch A1, so
the browser cannot reach Steam and a Cloudflare Worker passthrough has to exist before any
of the UI can be tested against real data. Scope:

- One route: `/?appid=<n>&cursor=<c>&…` → `store.steampowered.com/appreviews/<appid>`.
- **Param allowlist and a numeric-appid check.** Without them this is an open proxy for
  anything on Steam's domain — it must forward only the handful of params in §4.
- CORS headers scoped to the Pages origin, not `*`.
- Cloudflare **Cache API**, 30–60 min TTL keyed on the full param set. Steam's numbers
  barely move in an hour and this makes repeat opens free.
- **Its source lives in this repo this time** (`worker/`). The wishlist Worker's source was
  lost, which is the entire reason A1 is expensive today; do not repeat that.

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

---

## 12. Decisions — all closed

| # | decision | choice |
|---|---|---|
| 1 | sample size | **500** most recent (revisit if it proves too big) |
| 2 | sample mode | **recent** |
| 3 | prompt placement | **inline in the bundle**, top + bottom |
| 4 | review bombs | **included** — a publisher screw-up is legitimate signal; prompt reports it separately and gives both tallies |
| 5 | in-browser lexicon count | **dropped entirely** |
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
| Worker (outside this repo) | **only under branch A1** |
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

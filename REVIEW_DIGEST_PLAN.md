# Review Digest — design memo

**Status: PLAN ONLY. Nothing built yet.** This is the design record for a per-game,
on-demand pull of *real Steam review text*, packaged into one copy-paste block with an AI
prompt attached, so the user can get a quantitative issue breakdown of a game from actual
players instead of reading 300 reviews by hand.

Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md) (§1 design principles, §3.1 the
review-TEXT roadmap item this is adjacent to, §12 the Worker) · [ROADMAP.md](ROADMAP.md).

---

## 1. The flow

```
1. find a game            → existing search / filters, no change
2. hit "Reviews ⇩"        → new button on the card's details face
3. QTPD fetches N real reviews from Steam, live, in the browser
4. QTPD compacts them into one text block, AI prompt on top
5. Copy / Download .txt   → paste into any AI → quantitative answer
```

The benefit is step 3–4: **capture of most/all recent reviews stops being a manual
process.** QTPD does not do the summarizing — it does the *collection and packaging*, which
is the part that is tedious, mechanical, and currently impossible by hand.

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
| cost | free (rides an existing walk) | ~3–10 requests per click |
| storage | one small JSON | none |

§3.1 explicitly parked its Option **C** ("LLM one-line summary per game") because it "adds
an external-model dependency + cost + batch job, breaking the runs-entirely-free model."
The Review Digest gets C's payoff **without** that dependency: it exports the prompt and
lets the user's own AI do the inference. No model, no key, no cost, no batch job.

---

## 3. THE ONE BLOCKING UNKNOWN — does `appreviews` send CORS headers?

ARCHITECTURE §1 states flatly: *"Steam sends no CORS headers, so the browser cannot call
Steam directly."* That was established for the **storefront/wishlist** endpoints. It has
**not** been verified for `store.steampowered.com/appreviews/`, which is a different
endpoint, and the answer decides whether this feature needs a backend at all:

- **Branch A0 — CORS present.** Zero backend. The whole feature is client-side in
  `index.html`. No new job, no new data file, no Worker, nothing to deploy or keep alive.
- **Branch A1 — no CORS.** A Cloudflare Worker passthrough (~40 lines) that forwards
  `/?reviews=<appid>&cursor=…` to Steam and re-serves it with
  `Access-Control-Allow-Origin`. Same pattern and probably the same Worker project as the
  wishlist proxy (§12) — though note that Worker's source is **not in this repo and appears
  to be lost**, so A1 realistically means writing a new one.

**The probe cannot be run from a dev sandbox** — `store.steampowered.com` is blocked there
(verified: proxy returns 403 to CONNECT). Same situation as the trailer work, which was
resolved with a runner-side dump mode (`QTPD_DUMP_TRAILERS=1`). Do the same here.

**Crucially, this does not block starting.** The UI, the compaction, the format and the
prompt are identical in both branches, behind one function:

```js
async function fetchReviewPage(appid, params, cursor) { … }   // A0: Steam. A1: Worker.
```

Build everything against that seam; the probe only decides what goes inside it.

---

## 4. What Steam actually gives us

`GET https://store.steampowered.com/appreviews/<appid>?json=1` — public, **keyless**,
already used by three jobs in this repo (`scraper.py:506`, `playtime_refresh.py:531`,
`recent_refresh.py`).

**Parameters that matter:**

| param | values | note |
|---|---|---|
| `filter` | `recent` / `updated` / `all` | `recent` is the one that paginates deep and reliably; `all` is helpfulness-ranked and is documented as unstable past a few cursor pages — **verify in the probe** |
| `language` | `english` / `all` / … | see §6 |
| `review_type` | `all` / `positive` / `negative` | the basis for Balanced mode (§5) |
| `purchase_type` | `all` / `steam` / `non_steam_purchase` | repo jobs use `all` |
| `num_per_page` | max **100** | hard cap |
| `cursor` | `*` then echo | must be URL-encoded |
| `day_range` | 1–365 | only meaningful with `filter=all` |
| `filter_offtopic_activity` | `0` includes review bombs | Steam's default excludes them — see §8 |

**Per-review fields available** (audited in ARCHITECTURE §3.1 — we currently fetch all of
this on every playtime run and throw it away):

`recommendationid`, `review` *(the text)*, `voted_up`, `votes_up`, `votes_funny`,
`weighted_vote_score`, `comment_count`, `timestamp_created`, `timestamp_updated`,
`language`, `steam_purchase`, `received_for_free`, `written_during_early_access`,
`primarily_steam_deck`, and `author{ steamid, num_games_owned, num_reviews,
playtime_forever, playtime_at_review, last_played }`.

**`query_summary`** (first page, `cursor=*`) carries `total_reviews`, `total_positive`,
`total_negative`, `review_score_desc`. **This is the population anchor** and is what keeps
the AI's percentages honest (§5).

**Cost per digest:** 300 reviews = 3 requests. 1000 = 10. That is nothing.

---

## 5. Sampling — the honest-numbers problem

The user's ask ("count the issues, what share are technical") is a **quantitative claim**.
Hand an AI an arbitrary slice and its percentages describe *the slice*, not the game. This
is the single most important design decision in the feature, and it is a formatting
decision, not a code one.

**Rules:**

1. **Always print `query_summary` in the header.** The true split is stated at the top, so
   the AI can anchor and caveat rather than guess.
2. **State the sampling mode verbatim in the header**, so the AI cannot silently
   over-claim.
3. **Ask the prompt to report counts as "N of the 300 sampled"**, never as a bare percentage
   of the game.

**Modes:**

| mode | how | answers |
|---|---|---|
| **Recent** *(default)* | `filter=recent`, newest N | "what is this game like **now**" — the most defensible slice and what people actually want |
| **Balanced** | two passes, `review_type=positive` and `negative`, sampled **in the ratio of the true split** (a 90%-positive game gets ~90/10) | the only mode where "share mentioning X" genuinely transfers to the population |
| **Most helpful** | `filter=all&day_range=365` | quality over recency — the reviews other players voted up |
| **Negatives only** | `review_type=negative` | pure issue-mining; header must say **NOT REPRESENTATIVE** in caps |

Balanced should be built on `recent` + `review_type`, **not** on `filter=all`, for the
pagination-reliability reason in §4.

---

## 6. Compaction — the token problem

Raw, 1000 reviews ≈ 250 KB ≈ **~62k tokens**. Fine for Claude, far too big for a lot of
chat boxes. 300 reviews raw is ~75 KB ≈ ~19k tokens, which is comfortable everywhere. The
compaction pass buys roughly another 30–40% on top of that, and — more importantly —
removes content that actively *poisons the counting*.

| pass | what | why |
|---|---|---|
| **BBCode strip** | `[b] [i] [h1] [url=…] [quote] [spoiler] [list] [*] [strike] [table]` | Steam reviews are BBCode; the tags are pure token cost |
| **Whitespace collapse** | newlines → space, runs → one | reviews are full of decorative blank lines |
| **ASCII/emoji-art drop** | non-alphanumeric ratio > ~0.4 on a >80-char review, or >20 repeated identical chars | Steam is full of these, they are enormous, and they carry **zero** signal |
| **Near-duplicate drop** | hash of lowercased alphanumerics | copypasta ("publisher bad") appears verbatim hundreds of times and would skew **every single count** |
| **Per-review cap** | ~600 chars + ellipsis | the first 600 chars carry essentially all the complaint content; the tail is anecdote |
| **Min length** | drop <4 chars | keep the short ones — "runs terribly" is 3 tokens of pure signal |

**Every drop gets counted and printed in the header** (`excluded: 14 art, 6 dupes`). Same
principle as §5: the bundle never hides what it did to the sample.

---

## 7. Output format — a compact line protocol, not JSON

JSON roughly doubles the token count on braces, quotes and repeated keys, and buys nothing
here. One review per line:

```
=== QTPD REVIEW DIGEST ===
You are given real Steam reviews for one game. Instructions are at the BOTTOM.

GAME: Cyberpunk 2077  (appid 1091500)
ALL-TIME: Very Positive — 79% of 723,411 reviews  (571,494 ▲ / 151,917 ▼)
LAST 30 DAYS: 88% of 4,210
SAMPLE: 300 newest English reviews (filter=recent) · fetched 2026-08-28
  sample split: 241 ▲ / 59 ▼  (80% positive)
  excluded: 14 ASCII-art · 6 duplicates · 41 truncated at 600 chars
  language: english only (≈38% of this game's reviews are other languages)
LEGEND: ▲/▼ = recommends or not · Nh = hours played at time of review · date · ↑N = helpful votes

--- REVIEWS (300) ---
▲ 142h 2026-08-27 ↑31 | Best it's ever been. Holds 90fps on a 3070 since 2.3, the …
▼ 8h 2026-08-27 ↑4 | Crashes on every alt-tab with a DX12 device-removed error. Refunded.
▼ 61h 2026-08-26 ↑12 | Police AI still teleports behind you. Two years of patches …
…

--- INSTRUCTIONS ---
[the prompt]
```

**The prompt goes at the top AND the bottom.** A short framing line first (so the reader —
human or model — knows what they are looking at), the full instructions last (so they are
the most recent thing in context after a long paste). This is a known reliability pattern
for long pastes and costs ~200 tokens.

### The prompt (draft)

> These are real Steam reviews for the game named above, one per line.
>
> 1. **Verdict** — one paragraph: what is the consensus, and what is it conditional on.
> 2. **Issue table** — every distinct issue actually mentioned, with: issue · how many of
>    the sampled reviews mention it · % of the sample · % of the *negative* reviews in the
>    sample. Sort by count.
> 3. **Category rollup** — group every issue into exactly one of:
>    **Technical** (crashes, performance, bugs, drivers, Deck/Linux) ·
>    **Design** (balance, difficulty, pacing, controls, UI) ·
>    **Content** (length, repetition, endgame, missing features) ·
>    **Monetization** (MTX, DLC, pay-to-win, price) ·
>    **Service** (servers, always-online, anticheat, support).
>    Give a count and % of all issue mentions per category.
> 4. **Headline number** — what share of the complaints are *technical* vs everything else.
> 5. **Trend** — split the sample at its median date and compare. Is it getting better?
> 6. **Praise** — the top 3–5 things people consistently like.
> 7. **Caveat** — restate the sample size and mode, and that the counts describe the sample.
>    Where the all-time split above differs from the sample's, say so explicitly.
>
> Rules: count only what a review **actually says**. Do not infer, do not extrapolate, do
> not pad the list with issues you would expect this genre to have. If something is
> mentioned twice, it is 2. Ignore jokes and memes unless they encode a real complaint.

---

## 8. Risks and answers

| risk | answer |
|---|---|
| **Steam rate-limits the browser** (A0) | 10 requests is far under the ~200/5min budget; add 250–400 ms between pages, hard-cap at 1000, disable Fetch while one runs |
| **Worker IP is shared across all users** (A1) | Cloudflare Cache API keyed on appid+params, 30–60 min TTL. Steam's own numbers barely move in an hour, and it makes repeat opens free |
| **The scrapers' own budget** | Untouched under A0 (fetch comes from the *user's* IP). Under A1 it is the Worker's IP pool, not the runners' — still separate from the ~200/5min the jobs are already sitting at (`STEAM_DELAY = 1.5`) |
| **`filter=all` cursor unreliable past a few pages** | Build every deep mode on `filter=recent`; confirm the limit in the probe |
| **Review bombs** | `filter_offtopic_activity` — Steam's default excludes them. A review bomb is *exactly* the thing a summary should catch, so make it a visible toggle and print the setting in the header |
| **Non-English noise** | Default `english`; print the non-English share so the AI can caveat coverage |
| **ToS** | Public, keyless, documented endpoint the repo already calls in three jobs; output is a user-initiated copy for personal use; **no prose is cached in the repo** — which is also the storage answer from §2 |

---

## 9. UI — where it lives in `index.html`

- **Entry point (grid):** `.gi-actions` on the card's details face — `index.html:3973`,
  right next to the existing `Steam ↗`. Add **`Reviews ⇩`**.
- **Entry point (table):** a per-row action in Phase 2; the grid card is enough to ship.
- **Modal:** new `#revModal`. Reuse the `.pop-host` / `.pop-backdrop` styling at
  `index.html:1907`, but **not** `#popover` itself — that is the small filter/CSV editor and
  is the wrong size and lifecycle.
- **Controls:** mode (Recent / Balanced / Most helpful / Negatives) · size (100 / 300 / 1000)
  · language (English / All) · offtopic toggle → **Fetch**.
- **Progress:** `page 3/10 · 287 reviews · ~18k tokens`, live. Ten sequential requests is
  3–8 s and silence reads as broken.
- **Result:** readonly `<textarea>` preview + **Copy all** + **Download .txt** (reuse the
  Blob pattern at `index.html:4366`) + a live char/token estimate.
- **Abort:** `AbortController`; closing the modal cancels in flight.
- **Cache:** last few bundles in memory (and `sessionStorage`) so re-opening is instant.
- **Failure:** the existing `toast()` at `index.html:4417`, same voice as the wishlist
  failure path.

---

## 10. Phases

**Phase 0 — probe (must happen first; ~30 min).** `review_probe.py` +
`.github/workflows/review-probe.yml` (`workflow_dispatch`), runner-side because the sandbox
is blocked. It answers, in one run:
- Does `appreviews` return `Access-Control-Allow-Origin`? (`curl -I -H 'Origin: https://mlmariss.github.io'`) → **decides A0 vs A1**
- How deep does the `recent` cursor actually go before it repeats or dies?
- Do `review_type=positive|negative` paginate properly?
- Which fields are really present on a live payload?
- Dump one real 100-review sample to eyeball for the compaction thresholds in §6 — *dump
  first, then tighten*, exactly the lesson ARCHITECTURE §2.1 records from the trailer work.

**Phase 1 — MVP, client-only.** `fetchReviewPage` + compaction + formatter + modal + copy +
download. One mode: Recent / 300 / English. Ship it.

**Phase 2.** Balanced + Most-helpful + Negatives modes, size picker, offtopic toggle,
session cache, table-view entry point, non-English share.

**Phase 3 — optional.** Compare-two-games digest; a shareable link that re-runs the fetch;
and an **in-browser lexicon count** that does the technical/design tally locally, so QTPD
shows a number *before* any AI is involved — which is where this converges with the
ROADMAP §3.1 keyword item and where the two features finally share code.

---

## 11. Files touched

| file | change |
|---|---|
| `index.html` | one new ~400-line section: fetch, compact, format, modal |
| `review_probe.py` + `.github/workflows/review-probe.yml` | Phase 0 only; keep as a diagnostic or delete |
| Worker (outside this repo) | **only under branch A1** |
| `ARCHITECTURE.md` / `ROADMAP.md` | new section + cross-reference |

**No new data file. No new scheduled job. No change to any existing writer.** §1's
one-writer-per-file rule is untouched, and nothing here can interfere with the scrapers.

---

## 12. Open decisions — needed before Phase 1

1. **Default sample size** — 300 (recommended: ~19k tokens, fits everywhere) vs 500.
2. **Default mode** — Recent (recommended: answers "how is it *now*") vs Balanced (more
   statistically honest, twice the requests, and worse at catching a recent patch).
3. **Prompt placement** — inline in the bundle (recommended, one copy and done) vs a
   separate "copy prompt" button.
4. **Review bombs in or out by default.**
5. **Is Phase 3's in-browser lexicon count wanted at all?** It makes QTPD answer the
   question itself with no AI in the loop — and it is also the piece most likely to be
   wrong, because a hand-built lexicon has no idea what it is missing.

<!-- v9 -->
You are analysing real Steam reviews for one game. The game's name and the span of the sample
are on the `GAME:` and `REVIEWS:` lines at the very top of this bundle, above these
instructions, and repeated in the OVERVIEW block. Below these instructions you will find that
OVERVIEW block, a TIMELINE block, a TOPIC MENTIONS block, then the reviews, one per line.
A READER FOCUS block may also appear directly under these instructions; if it does, it is
binding and its rules override the caps below.

**The report opens with the game's name.** The reader runs several games in one sitting and
ends up with three or four of these in one conversation; a report that opens on a verdict and
never names its game is unusable to him. So the first line is
`# <the title from the GAME: line, copied character for character>` — never abbreviated, never
translated, never re-spelled from what you happen to know about the game, never the franchise
name in place of this edition's, and never with a subtitle trimmed off. The second line carries
the sample's date range and size. Both are copied, not recalled. If no `GAME:` line is present,
write `# (game name not in this bundle)` rather than guessing.

**The counts are the whole point of this report.** A description of what players think, with no
numbers attached, is worthless here — the reader could get that from reading five reviews
himself. What he cannot do by hand is count 500. That is your job.

So: **every issue row must carry a review count.** If you cannot count reliably, put the
INTEGRITY line at the TOP of the report, directly under the title lines, say what went wrong
and stop there. Do not quietly replace the tables with prose — that is the one failure mode
this report must not have. When the counting held up, INTEGRITY goes at the BOTTOM instead: it
is the receipt, not the finding, and nobody reading this came for it.

## Line format

`▲/▼  Nh  date  ↑N  [flags] | review text`

▲/▼ recommends or not · **Nh** hours played · date posted · **↑N** helpful votes ·
`[now]` posted inside the NOW window · `[top]` one of the most-upvoted reviews in the
sample · `[EA]` early access · `[free]` free/non-Steam copy · `[deck]` Steam Deck ·
`[upd]` edited later.

## How to count

1. **The unit is the review, not the mention.** A review complaining about crashes four times
   counts **once** for Crashes. One review can count in several different buckets.
2. **The denominator is the substantive-review count** from the OVERVIEW, for every
   percentage. Never switch denominators. There is exactly one exception and it is labelled
   in place: the Snapshot's `Dragging the score` row is a share of the ▼ reviews, because
   "what is costing this game its score" is a question about the negatives only.
3. **Use the fixed buckets below.** Do not invent, rename or split them. This is what makes
   the output comparable between games and between runs. The single headline row in rule 12
   is the one exception, and it overrides only the `Category` cell, never the `Bucket` one.
4. **The floor is `max(5 reviews, 2% of substantive)`,** rounded to the nearest whole review.
   State it once on the Issues table's Other line. Anything under it is not a row — it goes
   to the Other tally. Three reviews out of 500 is noise wearing a table row's clothes, and
   a fixed floor of 3 meant a 1000-review sample and a 300-review sample used the same bar.
   Reader-focus rows (READER FOCUS block, if present) are exempt and appear at any count,
   including 0.
5. **The `Quit / stayed` column** = of the reviews raising that issue, how many gave the game
   a ▼ overall and how many still gave it a ▲. Write it as raw counts — `13▼/1▲`, **▼ first,
   always** — never as a percentage. A percentage is unreadable without the sample's baseline
   negative rate; two raw numbers explain themselves. This column is what separates a
   dealbreaker (`13▼/1▲` — most people who hit it quit on the game) from a grumble
   (`1▼/3▲` — they mention it and recommend anyway) from something genuinely divisive
   (`10▼/10▲`). Never omit it, and never flip the order.
6. **A bucket counts complaints only.** A review that *praises* a thing does not go in that
   thing's issue row — praise belongs in the Loved column. Otherwise the split above is
   measuring two different populations mixed together and means nothing.
   The trap here is counting *mentions of a topic* as complaints. "Simple graphics, but I
   love it" is not a graphics complaint; it is praise with a shrug attached. Counting it as
   one is how a game with four real complaints about its art ends up reporting thirty.
7. **`Now` column = reviews carrying the `[now]` flag.** Every review inside the recent
   window is tagged, so this is a lookup, not a judgement. It is the difference between a
   problem the game still has and one it had at launch: a sample dominated by a launch
   spike will rank a long-dead complaint first on lifetime count alone. If an issue's `Now`
   count is near zero while its total is large, it has faded — say so in Notes rather than
   letting the row imply it is current.
8. **Never recompute the TIMELINE block.** Sentiment rates, the trend in points, the
   baseline ▼ rate and the quarterly figures are all computed for you. Copy them. Deriving
   them by hand from 500 dated lines is the single most error-prone thing you could do here,
   and getting the direction backwards would invert the report's conclusion.
9. **Obey the TIMELINE warnings, and never paper over a missing number.** `COVERAGE` says
   how much real time this sample covers — 500 reviews is two years of a quiet game and two
   days of a busy one, and the same "−15 pts" means opposite things in each. If `SPANS`
   warns the NOW window is a fortnight, or `COVERAGE` warns the sample is under two months,
   say so in the Snapshot instead of reporting a trend as though it were a trend. If the
   window was `narrowed`, the comparison is recent-vs-slightly-less-recent, not now-vs-launch.
   If TIMELINE prints **no** `TREND` line at all, write "no comparable earlier window in this
   sample" — never estimate one.
10. **TOPIC MENTIONS is a floor to check yourself against, not a source to copy.** It is a
   regex hit count, so it over-counts (praise matches too, and "zero crashes" matches
   Crashes) and under-counts (synonyms nobody listed). Use it in one direction only: after
   you have counted a bucket yourself, compare. If your number is below half the hits or
   above double them, you have probably missed something or double-counted — go back to the
   reviews, then say in Notes why the final number differs. **Never reproduce that table**,
   and never let a hit count stand in for a count you did not do.
   Its `▼/▲` column is the useful part: a topic at 42▼/12▲ against a 29% baseline is a
   complaint, the same topic at 12▼/42▲ is praise, and the raw hit count cannot tell them
   apart. A family with hits but no bucket in your table is a gap you should explain.
11. **READER FOCUS, when that block is present, outranks every cap in this file.** The reader
   named the things he is actually deciding on. Each one gets its own Issues row even at 0
   and even below the floor, and one clause in `### Who it's for`. A focus you leave out
   because "nobody mentioned it" is the single most useful row on the page — it is the
   answer *no*, and he cannot get it any other way. Report counts and nothing else on a
   focus: no defending it, no condemning it, no advice about whether he should care.
12. **The headline row.** When one *concrete* complaint — a specific thing players name, not
   a bucket — is raised by more than 8% of substantive reviews, give it a row whose
   `Category` is free text in the players' own words, and sort it **first, above everything,
   regardless of its `Now` count.** At most one per report; if two qualify, take the larger.
   Its `Bucket` cell still holds whichever fixed bucket fits best, and Notes says which other
   buckets it was drawn from.
   This exists because the fixed taxonomy can shred one dominant grievance into three
   forgettable rows. Measured case: a game where the required Microsoft account is ~12% of
   substantive reviews and 30% of every ▼ review in the sample, split across *Always-online &
   DRM*, *Support & communication* and *Crashes & launch* — so the thing the game is most
   criticised for appeared nowhere as one thing.

## The buckets — every complaint goes in exactly one

**Technical** — Crashes & launch · Performance & frame rate · Bugs & glitches ·
Save or progress loss · Controller & platform support

**Design** — Grind & pacing · Difficulty & balance · Combat & controls · UI & quality-of-life ·
Co-op & multiplayer design (tethering, instancing, shared progress) ·
Hostile mechanics (griefing, raids, losing your work)

**Content** — Thin or too short · Repetitive or filler · Story & writing · Missing or cut features

**Monetization** — Price & value · DLC, paywalls & microtransactions

**Service** — Servers & connectivity · Always-online & DRM · Support & communication

Anything fitting none of these goes in the Other tally. If Other would be your biggest row,
say so in Notes — it means these buckets are wrong for this game.

## OUTPUT — copy this skeleton exactly and fill in every `< >`

The order is the point: **the title says which game, the first screen is the answer, and
everything after it is the evidence.** The Issues table comes last because it is the working,
not the finding, and INTEGRITY comes after even that because it is the receipt.

Do not add sections. Do not rename them. Do not reorder them. Do not write an executive
summary, an introduction, a methodology note, or a closing paragraph. Leave a blank line
before every table — without one, strict Markdown renderers drop the table and print raw
pipes. This skeleton, and nothing else:

```
# <game title, copied character for character from the GAME: line>
*Steam reviews <first date> to <last date> · <N> reviews sampled · appid <N>*

### Snapshot

| Field | Value |
|---|---|
| Verdict | <12 words max> |
| Right now | <N>% positive across the NOW window, <improving / flat / worsening> (<+N or -N> pts vs before) — both copied from TIMELINE; if TIMELINE warns the window is thin or short, say "too recent to call" instead of a direction |
| Best at | <the top Loved row> (<N> reviews) |
| Most pressing | <the issue with the highest Now count> (<N> now / <N> total) |
| Dragging the score | <top issue> — <N>% of all ▼ reviews, <rising / flat / falling> vs before |
| Sentiment | <N>% positive across the sample, vs <N>% all-time |
| Sample | <N> reviews, <N> substantive, <date> to <date> |
| Sample reach | <N> days of reviews, ~<N> per month — copied from COVERAGE |
| Complaint rate | <N>% of substantive reviews raise at least one issue |
| Baseline ▼ rate | <N>% — copied from TIMELINE, for judging the splits below |
| Technical share | <N>% of all complaints |
| Campaign | <none, or: <N> reviews, <date range>> |

### Who it's for

**Buy it if you** — <trait>; <trait>; …
**Skip it if you** — <trait>; <trait>; …

### Loved vs hated

| # | Loved | N | Hated | N |
|---|---|---:|---|---:|
| 1 | <thing> | <N> | <thing> | <N> |

### Where the complaints land

| Bucket | Reviews raising ≥1 | % subst |
|---|---:|---:|
| Technical | <N> | <N>% |
| Design | <N> | <N>% |
| Content | <N> | <N>% |
| Monetization | <N> | <N>% |
| Service | <N> | <N>% |

### Notes
- <max 5 bullets, one line each — only what a number cannot carry>

### Issues

| Bucket | Category | Reviews | Now | % subst | Quit / stayed | What they say |
|---|---|---:|---:|---:|---|---|
| <bucket> | <category> | <N> | <N> | <N>% | <N>▼/<N>▲ | <8 words max> |

*Quit / stayed — of the reviewers who raised this: how many refused to recommend / recommended anyway.*

Floor: <N> reviews. Other or below floor: <N> reviews.

---
INTEGRITY: read <N> of <N> reviews · denominator <N> substantive · <OK, or what went wrong>
```

**The title lines** — `# <name>`, then one italic line carrying the sample's date range, its
review count and the appid, all copied from the `GAME:` and `REVIEWS:` lines at the top of the
bundle and the OVERVIEW's `SAMPLE` lines. Nothing editorial in either: no verdict, no adjective,
no score. The reader is using these two lines to tell four reports apart at a glance, and two
runs over the same game differ only by the second one, so neither is optional and neither is
the place for a finding.

**`### Snapshot`** — the first five rows are the answer; the rest is the evidence. Fill them
in that order. The header row must read `| Field | Value |`: an empty `| | |` header is
dropped whole by strict renderers, taking the table with it.

**`### Who it's for`** — max four clauses on each line, semicolon-separated. Every
`Skip it if you` clause must trace to an Issues row that cleared the floor, or to a TOPIC
MENTIONS family that has hits. **No clause may be inferred from the genre** — "skip it if you
dislike roguelikes" is not a finding, it is a description of the store page. If a READER
FOCUS block is present, each focus gets one clause here, on whichever side its count supports.

**`### Loved vs hated`** — max 5 rows. The two columns are ranked **independently**: row 3's
Loved and row 3's Hated have nothing to do with each other beyond both being third. It sits
this high because what a game is loved for is half the buying decision, and a praise list
buried under the issue table never gets read.

**`### Where the complaints land`** — all five buckets, always, in the order above, even at
zero. Counted **at review level**: a review complaining about two Technical things counts
once for Technical. Because one review can land in several buckets, this column does not sum
to the complaint rate, and it is not supposed to.

**`### Issues`** — max 10 rows, plus any reader-focus rows, plus the headline row if one
qualifies. **Sort by `Now`, then by Reviews**, with the headline row pinned first — the
reader is buying the game today, so what is still being complained about outranks what once
was.

**`INTEGRITY`, last** — one line under a `---` rule, after everything else, saying how many
reviews you read, the denominator you used, and `OK` or what went wrong. It is here rather
than at the top because it answers a question about the report, not about the game. The one
exception is the failure case above: counting you cannot trust moves it to the top, directly
under the title lines, where it stops the report instead of footnoting it.

Use Notes only where it changes the picture: an issue whose `Now` count has collapsed, so the
table's total overstates it; a top complaint that is really an **expectation mismatch** —
people wanting a different game rather than reporting a fault — and what the store page fails
to warn them about; a campaign worth separating (with which issue ranks move if excluded);
`[EA]` complaints that may already be fixed; `[deck]` or `[free]` players differing from the
rest (the splits are in TIMELINE); whether the loudest critics are experienced (high `Nh`) or
drive-by; **what the `[top]` reviews are about** — if the most-upvoted reviews in the sample
are one complaint, that complaint is what a buyer reads on the store page whatever its rank
here; **the Other tally when it is the largest row** — that means these buckets are wrong for
this game and the reader should know the table is hiding something; which buckets a headline
row was drawn from; any bucket where your count diverges sharply from TOPIC MENTIONS, and
why; any way this sample misleads about the game overall. If none apply, write "None."

## Rules

- **Count only what a review actually says.** Never infer or extrapolate, and never add an
  issue the genre would suggest. If nobody said it, it does not exist.
- **Short reviews are real — but check whether they are still here.** The OVERVIEW carries a
  `quality bar:` line when the reader asked for one. Without it, the sample holds everything
  Steam returned: many reviews are a few words, they count toward sentiment and usually carry
  no issue, which is why percentages use the substantive count. With it, reviews under that
  word count were removed *before the sample was built* — so every count you make is over
  people who said something, and the sample is smaller than the game's review total for that
  period by design. The `before the bar:` line prints the unfiltered ▲/▼ split so you can see
  what the filter cost; it is context, not a figure to report. Quote the sample split.
- **Ignore jokes and memes** unless they carry a real complaint.
- **Do not soften anything.** If the picture is bad, the Verdict says it is bad.
- **Length is not thoroughness.** Exceeding the caps is a failure.

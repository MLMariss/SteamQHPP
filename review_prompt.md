<!-- v6 -->
You are analysing real Steam reviews for one game. Below these instructions you will find an
OVERVIEW block, a TIMELINE block, a TOPIC MENTIONS block, then the reviews, one per line.

**The counts are the whole point of this report.** A description of what players think, with no
numbers attached, is worthless here — the reader could get that from reading five reviews
himself. What he cannot do by hand is count 500. That is your job.

So: **every issue row must carry a review count.** If you cannot count reliably, say so on the
INTEGRITY line and stop. Do not quietly replace the tables with prose — that is the one
failure mode this report must not have.

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
   percentage. Never switch denominators.
3. **Use the fixed buckets below.** Do not invent, rename or split them. This is what makes
   the output comparable between games and between runs.
4. **Floor of 3.** Fewer than 3 reviews is not a row — add it to the Other tally.
5. **▼/▲ split** = of the reviews raising that issue, how many gave the game a ▼ overall and
   how many still gave it a ▲. Write it as raw counts — `13▼/1▲` — never as a percentage. A
   percentage is unreadable without the sample's baseline negative rate; two raw numbers
   explain themselves. This column is what separates a dealbreaker (`13▼/1▲` — most people
   who hit it quit on the game) from a grumble (`1▼/3▲` — they mention it and recommend
   anyway) from something genuinely divisive (`10▼/10▲`). Never omit it.
6. **A bucket counts complaints only.** A review that *praises* a thing does not go in that
   thing's issue row — praise belongs in the Praise table. Otherwise the split above is
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

Do not add sections. Do not rename them. Do not reorder them. Do not write an executive
summary, an introduction, a methodology note, or a closing paragraph. This skeleton, and
nothing else:

```
INTEGRITY: read <N> of <N> reviews · denominator <N> substantive · <OK, or MISMATCH — stopping>

### Snapshot
| | |
|---|---|
| Verdict | <12 words max> |
| Right now | <N>% positive across the NOW window, <improving / flat / worsening> (<+N or -N> pts vs before) — both copied from TIMELINE; if TIMELINE warns the window is thin or short, say "too recent to call" instead of a direction |
| Best at | <the top Praise row> (<N> reviews) |
| Most pressing | <the issue with the highest Now count> (<N> now / <N> total) |
| Sentiment | <N>% positive across the sample, vs <N>% all-time |
| Sample | <N> reviews, <N> substantive, <date> to <date> |
| Sample reach | <N> days of reviews, ~<N> per month — copied from COVERAGE |
| Complaint rate | <N>% of substantive reviews raise at least one issue |
| Baseline ▼ rate | <N>% — copied from TIMELINE, for judging the splits below |
| Technical share | <N>% of all complaints |
| Campaign | <none, or: <N> reviews, <date range>> |

The first four rows are the answer; the rest is the evidence. Fill them in that order.

### Issues
| Bucket | Category | Reviews | Now | % subst | ▼/▲ | What they say |
|---|---|---|---|---|---|---|
| <bucket> | <category> | <N> | <N> | <N>% | <N>▼/<N>▲ | <8 words max> |

Max 10 rows, none below 3 reviews. **Sort by `Now`, then by Reviews** — the reader is buying
the game today, so what is still being complained about outranks what once was.
Other or below floor: <N> reviews.

### Praise
| What they praise | Reviews | % subst |
|---|---|---|
| <thing> | <N> | <N>% |

Max 5 rows.

### Notes
- <max 5 bullets, one line each — only what a number cannot carry>
```

Use Notes only where it changes the picture: an issue whose `Now` count has collapsed, so the
table's total overstates it; a top complaint that is really an **expectation mismatch** —
people wanting a different game rather than reporting a fault — and what the store page fails
to warn them about; a campaign worth separating (with which issue ranks move if excluded);
`[EA]` complaints that may already be fixed; `[deck]` or `[free]` players differing from the
rest (the splits are in TIMELINE); whether the loudest critics are experienced (high `Nh`) or
drive-by; **what the `[top]` reviews are about** — if the most-upvoted reviews in the sample
are one complaint, that complaint is what a buyer reads on the store page whatever its rank
here; any bucket where your count diverges sharply from TOPIC MENTIONS, and why; any way this
sample misleads about the game overall. If none apply, write "None."

## Rules

- **Count only what a review actually says.** Never infer or extrapolate, and never add an
  issue the genre would suggest. If nobody said it, it does not exist.
- **Short reviews are real.** Many are a few words; they count toward sentiment but usually
  carry no issue, which is why percentages use the substantive count.
- **Ignore jokes and memes** unless they carry a real complaint.
- **Do not soften anything.** If the picture is bad, the Verdict says it is bad.
- **Length is not thoroughness.** Exceeding the caps is a failure.

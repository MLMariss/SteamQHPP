<!-- v3 -->
You are analysing real Steam reviews for one game. Below these instructions you will find an
OVERVIEW block, then the reviews, one per line.

**The counts are the whole point of this report.** A description of what players think, with no
numbers attached, is worthless here — the reader could get that from reading five reviews
himself. What he cannot do by hand is count 500. That is your job.

So: **every issue row must carry a review count.** If you cannot count reliably, say so on the
INTEGRITY line and stop. Do not quietly replace the tables with prose — that is the one
failure mode this report must not have.

## Line format

`▲/▼  Nh  date  ↑N  [flags] | review text`

▲/▼ recommends or not · **Nh** hours played · date posted · **↑N** helpful votes ·
`[EA]` early access · `[free]` free/non-Steam copy · `[deck]` Steam Deck · `[upd]` edited later.

## How to count

1. **The unit is the review, not the mention.** A review complaining about crashes four times
   counts **once** for Crashes. One review can count in several different buckets.
2. **The denominator is the substantive-review count** from the OVERVIEW, for every
   percentage. Never switch denominators.
3. **Use the fixed buckets below.** Do not invent, rename or split them. This is what makes
   the output comparable between games and between runs.
4. **Floor of 3.** Fewer than 3 reviews is not a row — add it to the Other tally.
5. **▼ share** = of the reviews raising that issue, the percentage that were ▼. This is what
   separates a dealbreaker from a grumble inside an otherwise positive review. Never omit it.

## The buckets — every complaint goes in exactly one

**Technical** — Crashes & launch · Performance & frame rate · Bugs & glitches ·
Save or progress loss · Controller & platform support

**Design** — Grind & pacing · Difficulty & balance · Combat & controls · UI & quality-of-life ·
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
| Sample | <N> reviews, <N> substantive, <date> to <date> |
| Sentiment | <N>% positive, vs <N>% all-time |
| Complaint rate | <N>% of substantive reviews raise at least one issue |
| Biggest issue | <bucket> (<N> reviews) |
| Technical share | <N>% of all complaints |
| Trend | <improving / flat / worsening> (<+N or -N> pts) |
| Campaign | <none, or: <N> reviews, <date range>> |

### Issues
| Bucket | Category | Reviews | % subst | ▼ share | What they say |
|---|---|---|---|---|---|
| <bucket> | <category> | <N> | <N>% | <N>% | <8 words max> |

Max 10 rows, sorted by review count, none below 3 reviews.
Other or below floor: <N> reviews.

### Praise
| What they praise | Reviews | % subst |
|---|---|---|
| <thing> | <N> | <N>% |

Max 5 rows.

### Notes
- <max 5 bullets, one line each — only what a number cannot carry>
```

Use Notes only where it changes the picture: a campaign worth separating (with which issue
ranks move if excluded); `[EA]` complaints that may already be fixed; `[deck]` players
differing from desktop; `[free]` sentiment differing from paying players; whether the loudest
critics are experienced (high `Nh`) or drive-by; any way this sample misleads about the game
overall. If none of those apply, write "None." and stop.

## Rules

- **Count only what a review actually says.** Never infer or extrapolate, and never add an
  issue the genre would suggest. If nobody said it, it does not exist.
- **Short reviews are real.** Many are a few words; they count toward sentiment but usually
  carry no issue, which is why percentages use the substantive count.
- **Ignore jokes and memes** unless they carry a real complaint.
- **Do not soften anything.** If the picture is bad, the Verdict says it is bad.
- **Length is not thoroughness.** Exceeding the caps is a failure.

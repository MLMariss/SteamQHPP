<!-- v2 -->
You are analysing real Steam reviews for one game. Below these instructions you will find an
OVERVIEW block, then the reviews, one per line.

Produce a **short, scannable, quantitative** report. A reader should get the picture in about
thirty seconds. Tables, not prose. Do not exceed the caps below — going over is a failure, not
thoroughness.

## Line format

`▲/▼  Nh  date  ↑N  [flags] | review text`

▲/▼ recommends or not · **Nh** hours played · date posted · **↑N** helpful votes ·
`[EA]` early access · `[free]` free/non-Steam copy · `[deck]` Steam Deck · `[upd]` edited later.

## How to count — follow this exactly, or the numbers mean nothing

1. **The unit is the review, not the mention.** A review that complains about crashes four
   times counts **once** for Crashes. One review can count in several different buckets.
2. **The denominator is the substantive-review count** from the OVERVIEW. Use it for every
   percentage. Never switch denominators mid-report.
3. **Use the fixed buckets below.** Do not invent new ones, do not split a bucket into
   variants, do not report an issue outside them. This is what makes the output comparable
   between games and between runs.
4. **Floor of 3.** A bucket with fewer than 3 reviews is not listed; add it to `Other`.

## The buckets — every complaint goes in exactly one

**Technical** — Crashes & launch failures · Performance & frame rate · Bugs & glitches ·
Save or progress loss · Platform, controller & input support

**Design** — Grind & pacing · Difficulty & balance · Combat & controls · UI & quality-of-life ·
Hostile mechanics (griefing, raids, losing your work)

**Content** — Too short or thin · Repetition & filler · Story & writing · Missing or cut features

**Monetization** — Price & value · DLC & paywalls · Microtransactions & pay-to-win

**Service** — Servers & connectivity · Always-online & DRM · Developer communication & support ·
Anti-cheat

Anything that genuinely fits none of these goes in a single **Other** row. If `Other` is your
biggest row, say so — it means these buckets are wrong for this game.

## Output — exactly these four sections, in this order

### 1. Integrity check (three lines, first, always)

- Reviews in the OVERVIEW vs reviews you actually read.
- Substantive count you used as the denominator.
- **If these do not match, say so plainly and stop.** A partial read makes every number
  below false. Do not quietly analyse a fraction of the file.

### 2. Snapshot — one two-column table, max 8 rows

Verdict (≤12 words) · Sample size and date span · Sample sentiment vs the game's all-time score ·
Complaint rate (share of substantive reviews raising ≥1 issue) · Largest bucket · Technical share
of all complaints · Trend · Campaign present, yes/no.

### 3. Issues — one table, **max 10 rows**, sorted by review count

| Bucket | Category | Reviews | % subst. | ▼ share | What they say |

- **▼ share** — of the reviews raising this, the share that were ▼. This separates a
  dealbreaker from a grumble inside an otherwise positive review, and is the most useful
  column in the table. Never omit it.
- **What they say** — at most eight words. No sentences, no commentary.
- Below the table, one line: how many further reviews fell into `Other` or below the floor.

### 4. Praise — one table, max 5 rows

| What they praise | Reviews | % subst. |

### 5. Notes — at most 5 bullets, one line each

Only things a number cannot carry. Include a bullet **only if it changes the picture**:

- A campaign: its count, its date range, and which issue ranks move if you exclude it.
  If none, the Snapshot row already said so — write nothing here.
- `[EA]` complaints that may already be fixed, if there are enough to matter.
- `[deck]` problems, if Deck players differ from desktop.
- `[free]` sentiment, if it differs from paying players.
- Whether the loudest critics are experienced (high `Nh`) or drive-by (low `Nh`).
- Any way the sample misleads about the game as a whole.

## Rules

- **Count only what a review actually says.** Never infer, extrapolate, or add issues the
  genre would suggest. If nobody said it, it does not exist.
- **Short reviews are real.** Many reviews are a few words. They count toward sentiment but
  usually carry no issue — which is why percentages use the substantive count.
- **Ignore jokes and memes** unless they carry a real complaint.
- **Do not soften anything.** If the picture is bad, say it is bad, in the Verdict.
- **No preamble, no methodology essay, no closing summary.** The four sections and nothing
  else. If you want to explain a judgement call, it goes in Notes as one bullet.

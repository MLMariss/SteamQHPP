<!-- v1 -->
You are analysing real Steam reviews for one game. The reviews are above, one per line.

Read the SAMPLE block in the header before anything else: it tells you how many reviews you
were given, how they were selected, and how many carry enough text to analyse. Every count
you report is a count **of that sample**, never of the game as a whole.

## Line format

`▲/▼  Nh  date  ↑N  [flags] | review text`

- **▲ / ▼** — the player recommends the game, or does not.
- **Nh** — hours played at the time of writing.
- **date** — when it was posted.
- **↑N** — how many other players marked it helpful.
- **flags** — `[EA]` written during early access · `[free]` free or non-Steam copy ·
  `[deck]` played mainly on Steam Deck · `[upd]` edited after first posting.

## What to produce

**1. Verdict.** One paragraph. What is the consensus, and what is it conditional on
(hardware, patch version, expectations, playstyle)?

**2. Issue table.** Every distinct problem players actually mention. Columns: issue ·
reviews mentioning it · % of the sample · % of the ▼ reviews. Sort by count, highest first.

**3. Category rollup.** Put every issue in exactly one bucket, with a count and a share of
all issue mentions:

- **Technical** — crashes, performance, frame rate, bugs, drivers, load times
- **Design** — balance, difficulty, pacing, controls, UI, AI
- **Content** — length, repetition, empty endgame, missing or cut features
- **Monetization** — microtransactions, DLC, pay-to-win, price
- **Service** — servers, always-online, anti-cheat, support, account requirements

**4. The headline number.** What share of all complaints are Technical, versus everything
else combined? State it plainly in one sentence.

**5. Campaign check.** Off-topic and review-bombing reviews are deliberately *included* in
this sample, because a publisher or developer doing something people are angry about is real
information. But it is a different fact from a crash bug, so separate it:

- Is there a spike of reviews about something other than playing the game — a publisher
  decision, DRM, a price change, a politics or platform dispute? Give its count and the date
  range it clusters in.
- If there is, present the issue table **twice**: once including those reviews, once
  excluding them. Say which issues change rank between the two.
- If there is no such spike, say so in one line and move on.

**6. Trend.** Split the sample at its median date and compare the halves. Is sentiment
improving, worsening, or flat, and which specific issues appear or disappear? `[upd]`
reviews are direct evidence — someone went back and changed their verdict.

**7. Read the flags.** These change what a review means, so use them:

- `[EA]` — early-access complaints about missing content may already be resolved. Report
  EA-era issues separately from current ones; do not blend them into one tally.
- `[deck]` — report Steam Deck performance complaints separately from desktop ones. They are
  different problems with different causes.
- `[free]` — these players did not pay. Check whether their sentiment differs from the rest,
  and say so if it does.
- Long-playtime reviewers (high `Nh`) know the late game. Weight them for depth complaints,
  and low-hour reviewers for first-impression and launch problems.

**8. Praise.** The three to five things players consistently like.

**9. Caveat.** Close by restating: the sample size and how it was selected, how many reviews
had enough text to analyse, and the game's overall score from the header. Where the sample's
positive/negative split differs from the game's all-time split, say so and offer the likely
reason.

## Rules

- **Count only what a review actually says.** Do not infer, extrapolate, or add issues you
  would expect this genre to have. If nobody mentioned it, it is not in the table.
- **Mentioned twice is 2.** Do not merge distinct complaints to tidy the list, and do not
  split one complaint into several to pad it.
- **Short reviews are real.** A large share of Steam reviews are a few words ("good", "gg",
  "refunded"). They count toward sentiment. They mostly cannot carry an issue, which is why
  the header reports how many reviews are substantive — issue percentages should be read
  against that number, and you should say so.
- **Ignore jokes and memes** unless they encode an actual complaint.
- **Do not soften the findings.** If the picture is bad, say it is bad.
- If you are unsure whether something is one issue or two, say so rather than picking
  silently.

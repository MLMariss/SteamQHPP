# QTPD — Ineska improvement list

First-time-user feedback on the live site, collected as a running comment thread with
screenshots. Ineska is an outside reviewer: no prior exposure to the app, no knowledge of
the data model, arriving cold at `mlmariss.github.io/SteamQTPD/` on a 1028px-wide desktop
window, incognito, in Chrome.

**What this file is.** The raw findings, one per item: what was pointed out, what the
underlying problem is, and where in the code it lives. It is a *capture* document — the
value is that nothing gets lost between the chat thread and a fix.

**What this file is not.** It is not a decision record and not a commitment. Fixes are
proposed per item and reviewed before anything is implemented; the `Fix` line stays
`pending review` until a direction is accepted. Once an item ships it gets annotated
`[Done]` and stays here as a record so it isn't re-raised.

**Why it deserves its own file** rather than a `ROADMAP.md` section: these are *usability*
defects observed by a real first-time user, not feature proposals. ROADMAP §3.x asks "is
there a data source, is it worth building"; this file asks "the thing we already built
confused somebody — why?". Different question, different bar, different lifecycle.

Comments were made in Latvian; each item keeps the original line verbatim so nothing is
lost in paraphrase, with an English gloss beneath it.

---

## Status index

| # | Item | Area | Status |
|---|---|---|---|
| 1 | View switcher reads as noise at the top of the page | Header / layout | Pending review |
| 2 | "Table view is desktop-only" is wrong on a 1028px desktop | Breakpoints | Pending review |
| 3 | Hover affordance inconsistent across the view switcher | Tooltips | Pending review |
| 4 | Gold card outline is unexplained | Grid view | Pending review |
| 5 | Expanded card overlay is not what was expected | Grid view | Pending review |
| 6 | Sort-direction control is a sentence, not an arrow | Sort UI | Pending review |
| 7 | QTPD wordmark toggles filters instead of going "home" | Header / reset | Pending review |
| 8 | Hover affordance inconsistent across grid cards | Grid view | Pending review |
| 9 | Bare `%` figures have no visible meaning | Grid view | Pending review |
| 10 | Card height jumps with longer titles | Grid view | Pending review |
| 11 | Accidental text selection can't be cleared | Grid view | Pending review |
| 12 | A fully-opened grid row collapses | Grid view | **Done** |
| 13 | Opened cards revert after scrolling away and back | Grid view | **Done** |

---

## 1 — View switcher reads as noise at the top of the page

**Said** (20:26):

> Sākumā viss, aiz kā uzreiz aizķeras acs un kas raisa jautājumus: Lai gan viss it kā
> rakstīts un tooltips salikti, vienalga kaut kā pirmais bija "dafaq is this". Manuprāt,
> šie iederas kaut kur tuvāk saturam.

*"First of all, the thing the eye immediately snags on and that raises questions: even
though everything is written out and the tooltips are in place, my first reaction was still
'dafaq is this'. In my opinion these belong somewhere closer to the content."*

**Problem.** `Table / Card / Grid / CSV` sits in the top header bar, far from the results it
governs. It is the first cluster the eye lands on, before the user has seen a single game,
so it is being read with zero context — at that moment "Table/Card/Grid" are four unexplained
words. Labels and `title=` tooltips do not fix this, because the confusion is about
*relevance*, not about wording: the control answers a question the user has not asked yet.

**Where.** `index.html` — `#viewSwitch` in the header (~L1136–L1142).

**Fix.** Pending review.

---

## 2 — "Table view is desktop-only" is wrong on a 1028px desktop

**Said** (20:27), on the toast shown when Table is clicked at 1028px:

> Pardon my french..? :D 1028px screen joprojām ir desktop. :D

*"Pardon my french..? A 1028px screen is still desktop."*

**Problem.** The message says *desktop-only* but the actual gate is a **width** threshold:
`matchMedia("(max-width:1374px)")` flips the layout to card. The table itself has a hard
`min-width:1324px` (1218px with the Tags column collapsed), so it genuinely does not fit at
1028px — the mechanism is correct, the explanation is not. Telling a desktop user their
desktop isn't a desktop reads as a bug in the app, not as a constraint of the layout. The
same wording problem exists in the mirrored "Card view is mobile-only" toast.

**Where.** `index.html` — toast text (~L3628–L3630), `isNarrow()` (~L2493), table
`min-width` (~L410–L412).

**Fix.** Pending review.

---

## 3 — Hover affordance inconsistent across the view switcher

**Said** (20:28, on the CSV button showing a tooltip):

> Action uz hover ir.

*"There's an action on hover."*

**Said** (20:30, on Table / Card / Grid in the same row):

> A šitiem nav. Ta jā vai nē? :D

*"But these don't have one. So — yes or no?"*

**Problem.** Buttons sitting side by side in one control group behave differently on hover:
CSV gets the rich custom tooltip (styled panel, gold keyword, full sentence), while
Table/Card/Grid rely on the browser's native `title=` bubble — slower to appear, plain, and
visually unrelated. Two tooltip systems in a four-button row makes the row look
half-finished and makes the user doubt which buttons are actually interactive.

**Where.** `index.html` — `#viewSwitch` buttons use `title=` (~L1138–L1139); the custom tip
engine is the `TIP` block (~L3930–L3950).

**Fix.** Pending review.

---

## 4 — Gold card outline is unexplained

**Said** (20:31), arrows drawn at two cards in the grid that carry a gold border while
neighbours don't:

> Nesaprotu, kāpēc daļai ir dzeltenā maliņa un daļai nav.

*"I don't understand why some have the yellow edge and some don't."*

**Problem.** There are in fact **two different gold cues** stacked on the same card edge and
nothing distinguishes them or explains either:

- `.gcard.sale` — a gold `border-color`, meaning the game is discounted right now.
- `.gcard.hi` — a gold `box-shadow` ring, applied when the card's QTPD value is in the top
  third of the current result set (`q >= state.qDomain * 0.66`).

They are near-identical visually, they can appear on the same card, and neither is
documented anywhere in the UI — no legend, no tooltip, no hover text. A user seeing a mixed
grid has no path to the answer.

**Where.** `index.html` — `.gcard.sale` / `.gcard.hi` CSS (~L803–L804), class assignment in
`gridCardHTML()` (~L2536).

**Fix.** Pending review.

---

## 5 — Expanded card overlay is not what was expected

**Said** (20:32), on the spec-sheet card view reached from the switcher:

> Nu vot čist nedomāju, ka šitā jābūt. :D

*"Well, I honestly didn't expect it to be like this."*

**Problem.** The detailed single-column view was not what the user anticipated from where
they clicked — the transition from a dense grid of box art to one tall stacked spec sheet
happens with no visual continuity and no indication that this is the *same data, different
density*. The switcher's `title=` ("Stacked spec-sheet cards") is not read at click time.
Related to item 1: the switcher is being operated before its options mean anything.

**Where.** `index.html` — `setView()` (~L2520), `body.layout-card` styles (~L942 onward).

**Fix.** Pending review.

---

## 6 — Sort-direction control is a sentence, not an arrow

**Said** (20:36), on the `↓ High → Low — flip` button in the sort popover:

> Wut? :D Vnk uz augšu/leju bultiņas divas vairs nav stilīgi?

*"Wut? Are two plain up/down arrows just not stylish enough any more?"*

**Problem.** A direction toggle is one of the most conventionalised controls on the web — an
arrow, or a pair of them. This one renders as a compound string that mixes **current state**
(`↓ High → Low`) with **the action** (`— flip`) in a single label, so the user has to parse
which half describes now and which half describes what happens on click. The conventional
control needs no parsing at all.

**Where.** `index.html` — sort popover action button (~L2794); the grid sort row has its own
direction button (~L3589, ~L3600).

**Fix.** Pending review.

---

## 7 — QTPD wordmark toggles filters instead of going "home"

**Said** (20:38), with an arrow at the `QTPD` logo showing its "Show / hide filters" tooltip:

> Šis ir neierasts risinājums. A ir kaut kāds veids, kā es varu dabūt uz sākuma skatu visu,
> ko es tur esmu sabakstījusi, ātri un vienkārši? 😅 Jo tas būtu tas, ko es no klikšķa uz
> QTPD sagaidītu.

*"This is an unusual solution. But is there some way to get everything I've poked at back to
the starting view, quickly and simply? Because that's what I'd expect from clicking QTPD."*

**Said** (20:41):

> Filtrus es varu resetot ar to linku, bet "Sorted by" man tāpat jāver vaļā un jāmēģina
> atcerēties, kas nu Tev tur bija pašā sākumā.

*"I can reset the filters with that link, but I still have to open 'Sorted by' and try to
remember what you had there in the first place."*

**Problem.** Two defects in one item:

1. **The wordmark does the wrong thing.** Clicking a site's logo means "take me back to the
   start" in essentially every web UI. Here it toggles the filter nav — a legitimate control,
   but bound to the one element with the strongest pre-existing expectation attached to it.
2. **There is no full reset.** `Reset all filters` clears filters, search and flags — but it
   does **not** restore `sortKey` / `sortDir`, and its own tooltip claims it resets "the sort
   back to their defaults", which is false. So a user who has changed the sort has no way
   back except remembering the original value. The second comment is exactly this: the reset
   link is found, and it is not enough.

**Where.** `index.html` — `#logoToggle` handler (~L3516), `#clear` handler (~L3520–L3537,
no sort reset), `#clear` tooltip claim (~L1162).

**Fix.** Pending review.

---

## 8 — Hover affordance inconsistent across grid cards

**Said** (20:44):

> Atkal dažiem action uz hover ir un dažiem nav.

*"Again, some have an action on hover and some don't."*

**Problem.** Same class of complaint as item 3, now inside the grid: hovering some parts of
a card produces a visible response and hovering others produces nothing. The card as a whole
is clickable (`cursor:pointer`, `role="button"`), but only certain sub-elements — the rating
`%`, the art — carry tooltips, so the hover response is patchy across a surface that is
uniformly interactive. The user cannot form a rule for what is hoverable.

**Where.** `index.html` — `.gcard:hover` (~L802), per-element `title=` in `gridCardHTML()`
(~L2542), grid click handler (~L3637–L3651).

**Fix.** Pending review.

---

## 9 — Bare `%` figures have no visible meaning

**Said** (20:46), arrow at the green `90%` on a card, tooltip reading *"Steam review score
90% · 15,917 revi…"*:

> Varbūt kādu ikonu klāt vai ko? Man no malas pirmajā brīdī vispār nav izpratnes, kas tie
> par %.

*"Maybe add some icon or something? Coming at it from outside, I have no idea at first what
those % are."*

**Problem.** The card shows a coloured `90%` with no label, no icon and no unit. Its meaning
— Steam all-time review score — exists **only** in the `title=` tooltip, so it is invisible
until hovered, and unavailable entirely on touch. The colour coding (`ratingColor()`) is
itself an unexplained second signal. A first-time user's most likely guesses are discount or
completion, neither of which is right, and there is nothing on screen to correct them.

**Where.** `index.html` — `.grate` render in `gridCardHTML()` (~L2540–L2543), `.grate` CSS
(~L831–L832).

**Fix.** Pending review.

---

## 10 — Card height jumps with longer titles

**Said** (20:49), with a screen recording of the grid resizing as content loads:

> Kad garāks nosaukums, lēkā bloku augstums. Tas parasti nav great.

*"When a title is longer, the block height jumps around. That's usually not great."*

**Problem.** `.gcard` has no fixed height — it is art (fixed `aspect-ratio:460/215`) plus an
info panel that grows with its content. `.gname` is clamped to two lines via
`-webkit-line-clamp`, so a one-line title and a two-line title produce cards of different
heights, and because CSS grid stretches every card in a row to the tallest one, a single
long title in a row re-heights that entire row. Scrolling through the grid therefore shows
a ragged, shifting rhythm rather than a stable one.

**Where.** `index.html` — `.gcard` / `.gart` / `.gcard .gmeta` / `.gname` (~L800–L834), grid
container `.gridview` (~L793–L794).

**Fix.** Pending review.

---

## 11 — Accidental text selection can't be cleared

**Said** (20:50), with the word "Price" highlighted blue on an opened card:

> Sīkums, bet kaitina: ja netīšam sanāk kaut ko iezīmēt, klikšķinoties, nevar vairs noņemt
> to sūdu. :D

*"A small thing, but it's annoying: if you accidentally select something while clicking, you
can't get rid of it any more."*

**Problem.** Repeated or double clicking on a card selects its text — the card is a click
target, so double-clicks happen naturally. Normally a click on empty space clears a
selection, but every click inside the grid is intercepted by the card handler
(`card.classList.toggle("open")`), so the usual "click elsewhere to deselect" gesture instead
flips cards open and closed while the highlight stays. Card labels are chrome, not content
anybody wants to copy, so the selection has no upside here.

**Where.** `index.html` — grid click handler (~L3637–L3651); no `user-select` rule on
`.gcard` (~L800).

**Fix.** Pending review.

---

## 12 — A fully-opened grid row collapses

**Said**, with a screenshot of a row of six opened cards squashed to a fraction of the
normal card height while the untouched cards beside them keep full size:

> In grid view — if all game cards in the row are opened, they all collapse how it is visible
> on the screen right now.

**Problem.** `.gcard.open` sets `display:none` on both `.gart` and `.gmeta`, and the details
panel `.ginfo` is `position:absolute; inset:0` — absolutely positioned, therefore
contributing **zero** height. An opened card has no content left in normal flow, so its
intrinsic height collapses to nothing. This is invisible as long as at least one card in the
row is still closed, because grid rows are sized by their tallest item and the closed card
holds the row open. Open *every* card in a row and there is nothing left to hold it: the row
shrinks to the height of the `.ginfo` content alone, and the layout visibly breaks.

**Where.** `index.html` — `.gcard.open` rules (~L835–L837), `.ginfo` (~L833–L834).

**Fix.** `[Done]` — `.gcard.open .gart, .gcard.open .gmeta` now hide with `visibility:hidden`
instead of `display:none`. Both boxes stay in flow at full size, so an open card is exactly as
tall as a closed one and opening or closing never moves the layout — the row cannot collapse
because there is always something holding its height, whether or not any card is still closed.

*Verified in Chromium at 1600px:* opening all six cards of a row left every height at 186px.
Before the fix the same row went 186px → 2px.

---

## 13 — Opened cards revert after scrolling away and back

**Said**:

> In grid view — if cards are opened and you scroll down some time and then come back up,
> some of those cards are reset/reversed back to original. That should not be the case — the
> selected (turned over) cards should remain the same no matter if the user is scrolling
> down or not.

**Problem.** Open/closed is stored **only** as a CSS class on a DOM node, and that node does
not survive. Scrolling down trips the infinite-scroll `IntersectionObserver`, which bumps
`state.pagesShown` and calls `render()`; `render()` rebuilds the grid with
`$("#gridview").innerHTML = games.map(gridCardHTML).join("")` — a complete replacement of
every card, including the ones already on screen and opened. The freshly generated markup
has no `open` class, so every opened card silently reverts. Any other re-render (filter
change, sort change, search) does the same. The state was never persisted anywhere it could
be restored from.

**Where.** `index.html` — `render()` grid branch (~L1978), `ensurePageObserver()`
(~L2194–L2210), open toggle (~L3650, ~L3653).

**Fix.** `[Done]` — open/closed moved out of the DOM and into `state.openCards`, a Set of
appids. `gridCardHTML()` re-applies the `open` class from that Set on every build, so a card
comes back open no matter how many times the grid is thrown away and rebuilt. Both toggles
(click and keyboard) and the Close button now go through one `setCardOpen(card, open)` helper
that writes the class *and* the Set together, so the two can't drift apart. This also covers
re-renders from filter, sort and search changes, which dropped the state for the same reason.

*Verified in Chromium:* six cards opened, scrolled down until pagination had grown the grid
from 100 to 1300 cards, scrolled back — all six still open. Before the fix all six had
reverted.

**Known sibling, not fixed here.** The 18+ art reveal (`.gcard.adult.revealed`) is stored the
same DOM-only way and is lost on exactly the same re-render — a revealed card re-blurs after
scrolling. Same cause, same shape of fix (a Set of revealed appids); left out because it is a
separate report. Raise it and it's a small change.

<!-- html-v9 -->
# OUTPUT FORMAT — one HTML page, instead of the Markdown skeleton

This block **replaces the output skeleton in the instructions above.** Everything above still
decides *what* you report and how you count it — the rules, the buckets, the floor, the caps,
the `[now]` lookup, the TIMELINE warnings, and the READER FOCUS block if one is present. Only
the rendering changes. **Do not produce the Markdown report as well.** One artefact, not two.

## What to return — a DOWNLOADABLE .html FILE

**Create and provide a downloadable HTML file** — one `.html` the reader saves out of your
reply in a single click, named after the game. Not a fenced code block, not markup pasted into
the reply, and **not a preview pane** — not an Artifact, not a document view. The reader asked
for an HTML page because they want the file: they are running several games and keeping the
pages side by side in a folder, so a panel they have to hunt a download button inside of is the
same manual work as a code block, one menu further away.

That is the whole test, and it is about the reader's downloads folder rather than about your
plumbing: **did a `.html` land there?** Every rule below only says how to get it there in the
chat you happen to be.

**Hand over the document, never a program that writes it.** This one is absolute and there is
no chat it does not apply to, Gemini's fallback rung included. A Python, JavaScript or shell
snippet that writes `<game>.html`, an `html_content = """..."""` string, a script with an
`open(...).write(...)` at the bottom, "run this to generate your page" — every one of those is
a wrong answer, and it is wrong even when the HTML inside the string is perfect. **If you have
a code tool, you run it yourself and hand over the file it produced; you never print the code
instead.** If you have no code tool, the answer is the raw HTML document. The reader has a
browser, not a Python interpreter, and a `.py` on their disk is not the page they asked for.
An HTML report was requested, so an HTML *file* is what has to arrive.

**The reply has to carry the document.** This check outranks everything else on this page, and
you run it on the reply you are about to send rather than on what you meant to do: **is the page
actually in it?** Three things count and nothing else does — a Canvas holding the document, a
file you genuinely attached, or one `html` block running from `<!DOCTYPE html>` to `</html>`. If
you cannot point at one of those in what you are sending, the reader gets **nothing**, and
nothing is the worst outcome available here: worse than a fence, worse than a `.py`. The sample
was pulled and pasted once; a reply that does not contain the report does not leave one behind.

**The reader's own page does the filing, so you do not have to.** The tool that built this
bundle also saves what you send back: the reader pastes your reply into it, it finds the
document, and it writes `<game>.html` into their downloads under exactly the right name. So the
naming is handled, the saving is handled, and **a document in one `html` block is a complete
answer** — not a consolation prize, and not something to apologise for. What that tool cannot do
is invent a page that is not there. Spend nothing on getting a *file* into their hands; spend
everything on the page itself, and make sure it is in the reply.

**Never announce a file instead of sending one, and never imitate the interface.** Do not write
a tag, a marker, a placeholder or a pseudo-element that looks like the chat's own UI reporting a
saved file — `<a_file_has_been_created_or_edited_view_it_in_the_drawer>`, "view it in the
drawer", "I've saved it to your files", a `sandbox:` link. Those messages belong to the
interface and only the interface can produce them; written out by you they are a claim, and the
reader believes it until they go looking and find an empty drawer. **If the words "I have
created the file" are in your reply, the document has to be in that same reply** — otherwise you
have handed over a description of the report in place of the report. And if you reached for a
document tool and what came back was a line of markup naming a file rather than a document you
can see, **that tool did not run**: the rung did not open, so take the next one and emit the
page.

**One chat reads the bans differently: Gemini.** Its bullet below is an ordered ladder of the
ways it can put a downloadable page in the reader's hands, and that ladder is binding for
Gemini — the bans on this page are written for the chats that attach a file to a reply, and
they do not overrule it. Every other chat reads the bans as written.

**Name the file after the game** — the game's title, lowercased, spaces and punctuation reduced
to single hyphens, `.html` on the end: *STAR WARS Zero Company™* becomes
`star-wars-zero-company.html`. That is what makes a folder of these readable.

- **Claude** — use the **file-creation / code tool**: write the complete document to
  `<game>.html` and attach it, so the reply carries a file the reader clicks to save.
  **Do not answer with an Artifact.**
- **ChatGPT** — use the **python tool**, which is ChatGPT's alone — **no other chat may reach
  for it, or imitate it by printing a Python block.** *Run* it to write `<game>.html` to disk
  and give the **download link**. The reply carries the link, never the script that made it.
  Not Canvas.
- **Gemini** — **create and provide a downloadable HTML file, `<game>.html`, and output it as
  the deliverable.** That is the ask stated as the outcome: the reader finishes with
  `star-wars-zero-company.html` saved from your reply, having selected no text. Read it as
  binding on **your reply** — the page arrives inside it, in Canvas or in the block. It never
  means announcing that a file exists somewhere the reader should go and look. Do not get
  there by imitating another chat's mechanism — in particular, **do not reach for ChatGPT's
  python tool and do not print a Python block that writes the file.** A printed program is not
  a downloadable file: the download icon on a `python` block saves a `.py`, so the reader ends
  up with a script instead of a page. Work down this ladder and stop at the
  **first rung that opens** — and *try* rung 1 before concluding it is shut:
  1. **Canvas.** Put the whole document into Canvas as an HTML file — the canvas holds the
     document itself, not code that generates it — and **title the canvas `<game>.html`**. That
     title is the filename Canvas's own **Download** hands the reader, which is the entire
     reason it matters. **This is how you create and provide a downloadable HTML file here**:
     Canvas is not a preview of the answer, its Download button *is* the handover, and the file
     it saves is the one the reader asked for. So this is your answer, and the "not a preview
     pane" rule above is written for Claude and ChatGPT, which attach files to a reply; it does
     not apply to you. Open Canvas and put the page in it — do not decide in advance that it is
     unavailable, and do not skip it because the document is long. Length is what it is for.
  2. **One `html` code block** — and *only* if Canvas will not open, which includes the case
     where you reached for it and got a marker naming a file instead of a document you can see.
     **The block is the document, not code that builds it**: it is tagged `html`, and
     its first characters are `<!DOCTYPE html>` and its last are `</html>`.
     A `python` block is not this rung and does not satisfy it — the download icon on a Python
     block saves a `.py`, so the reader ends up with a script they cannot run and no page at
     all. Emit the whole document in a single block and say, in your one sentence, *"click the
     download icon on the block to save it as `<game>.html`"*: Gemini's code blocks carry that
     icon, and it is the only reason this rung exists. It is Gemini's alone — no other chat may
     answer with a code block.

  Rung 2 is a fallback, not a preference. Answering with a code block while Canvas was there to
  open leaves the reader saving a file named after nothing, on a rung you were not entitled to.
  There is no rung 3. If both rungs are somehow shut, say so in plain words — do not invent a
  third answer out of another chat's tooling.
- **Anything else** — whatever writes a real file and hands it over, running the code itself
  rather than printing it. The test is the same everywhere: the reader ends up with a `.html`
  **in their downloads**, having selected no text, copied nothing, run nothing and clicked
  nothing but Save.

**Never fake the handover.** Do not write a download link for a file you did not actually
create with a tool, never a `sandbox:` URL unless that scheme is genuinely your own, and never
the interface's own file-saved message written out by hand. A link that resolves to a search
page or a 404, and a tag that announces a file into an empty drawer, are both worse than no
link at all: the reader believes the work arrived and finds out later that it did not.

If you cannot produce a file, **say so in plain words** and fall back to what you do have — on
Gemini that is the ladder above, Canvas first and the block only under it. An honest "I can't
attach files here, so the document is in the block below — use its download icon" is a good
answer. A confident link to nothing is not.

Beside the file, write **one short sentence at most** — which game the page covers. No preamble,
no "here's what I did", no summary of the findings underneath, and never a second copy of the
report pasted in as Markdown or as source. One artefact, not two.

Hard rules, all five load-bearing:

- **Self-contained.** One file, no dependencies. The `<style>` block below is the entire
  stylesheet. No external CSS, no web fonts, no images, no `<script>`, no CDN link, nothing
  the file has to fetch. It has to open with no network.
- **Copy the stylesheet verbatim.** Do not restyle it, do not "improve" it, do not add rules,
  do not switch the colours to match the game's box art. **Verbatim includes the whitespace:
  paste it line for line, in the order it is written — do not minify it, do not collapse the
  rules onto one line each, do not strip its section comments.** It renders the same either
  way, which is exactly why the shortcut is tempting; what it costs is that the two files stop
  being the same file — ten reports no longer share one stylesheet byte for byte, and anyone
  who opens the source to adjust a rule meets a wall instead of the sheet shown here. Its whole
  value is that ten reports on ten
  games look like ten pages of the same publication and can be read side by side. If a section
  seems to need a class this sheet does not have, you are inventing a section — go back and use
  the ones listed below.
- **The `<title>` is exactly `<game title> — Steam review digest`.** The game's title copied
  character for character from the GAME: line, an em dash, then those three words — not "Steam
  Review Analysis", not "Report", not the game on its own. That string is the browser tab, the
  bookmark and the window in the reader's dock, and a folder of ten pages is only navigable
  when all ten agree on the half that is constant.
- **Every number on the page is a number you counted.** The page is a rendering of the report
  you would otherwise have written in Markdown, not a new one with different figures. Nothing
  gets rounded differently, promoted, softened or dropped because it looks awkward in a table.
- **No charts and no interactivity.** The only graphics are the hero bar and the row minibars,
  and both are plain `<div>`s sized by an inline percentage. No `<canvas>` element, no SVG
  plots, no collapsible sections, no sorting.

## The skeleton — this is the file to build, not a block to paste back

Fill this in and write it to the `.html` you attach. The fence below is how the template is
shown to you here; it is not the shape of your answer.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><game title> — Steam review digest</title>
<style>
:root{
  --paper:#e9ecef;
  --card:#f6f7f9;
  --ink:#1d2126;
  --ink-soft:#5a6470;
  --rule:#c8ced6;
  --up:#4a7a4e;
  --down:#a4503c;
  --mark:#2f4858;
}
@media (prefers-color-scheme: dark){
  :root{
    --paper:#181c21;
    --card:#20252b;
    --ink:#e4e8ec;
    --ink-soft:#98a3af;
    --rule:#343b43;
    --up:#7fae82;
    --down:#d1826c;
    --mark:#a8c0cf;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--paper);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  font-size:16px;
  line-height:1.55;
  font-variant-numeric:tabular-nums;
}
.wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}

/* ---- masthead ---- */
.title{
  font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  font-weight:600;
  font-size:clamp(2rem,6vw,3.4rem);
  line-height:1.05;
  letter-spacing:-.015em;
  margin:0;
}
.sub{color:var(--ink-soft);font-size:.9rem;margin:.6rem 0 0}

/* ---- hero split bar ---- */
.hero{margin:2rem 0 2.75rem}
.bar{display:flex;height:2.75rem;border-radius:3px;overflow:hidden;background:var(--rule)}
.bar span{display:flex;align-items:center;color:#fff;font-size:.85rem;font-weight:600;padding:0 .7rem}
.bar .b-up{background:var(--up);justify-content:flex-start}
.bar .b-down{background:var(--down);justify-content:flex-end}
.hero-read{display:flex;flex-wrap:wrap;gap:.4rem 1.25rem;margin-top:.65rem;font-size:.88rem;color:var(--ink-soft)}
.hero-read b{color:var(--ink);font-weight:600}

/* ---- warning strip ---- */
.warn{
  border-left:3px solid var(--down);
  background:var(--card);
  padding:.8rem 1rem;
  font-size:.92rem;
  margin:0 0 2.5rem;
}

/* ---- sections ---- */
h2{
  font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  font-weight:600;font-size:1.4rem;letter-spacing:-.01em;
  margin:2.75rem 0 .9rem;padding-bottom:.4rem;border-bottom:1px solid var(--rule);
}
p{max-width:66ch}
.lede b{font-weight:600}

/* ---- tables ---- */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.92rem;min-width:36rem}
th,td{text-align:left;padding:.55rem .7rem;border-bottom:1px solid var(--rule);vertical-align:top}
thead th{
  font-size:.78rem;font-weight:600;color:var(--ink-soft);
  border-bottom:1px solid var(--ink-soft);white-space:nowrap;
}
td.n,th.n{text-align:right;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.snapshot table{min-width:0}
.snapshot th{width:12rem;font-weight:600;color:var(--ink-soft);font-size:.85rem}

/* ---- split minibar in issue rows ---- */
.split{display:flex;align-items:center;gap:.45rem;white-space:nowrap}
.minibar{display:flex;width:4.5rem;height:.55rem;border-radius:2px;overflow:hidden;flex:none}
.minibar i{display:block;height:100%}
.minibar .m-down{background:var(--down)}
.minibar .m-up{background:var(--up)}
.split small{font-size:.78rem;color:var(--ink-soft)}

/* ---- who it's for ---- */
.forwho{display:grid;gap:1rem;grid-template-columns:1fr 1fr}
@media (max-width:44rem){.forwho{grid-template-columns:1fr}}
.forwho div{background:var(--card);padding:1rem 1.1rem;border-radius:4px}
.forwho h3{margin:0 0 .45rem;font-size:1rem}
.forwho .buy h3{color:var(--up)}
.forwho .skip h3{color:var(--down)}
.forwho p{margin:0;font-size:.94rem}

/* ---- notes ---- */
ul.notes{padding-left:1.1rem;max-width:66ch}
ul.notes li{margin-bottom:.4rem}

/* ---- integrity ---- */
.integrity{
  margin-top:3rem;padding-top:1rem;border-top:1px solid var(--rule);
  font-size:.85rem;color:var(--ink-soft);max-width:66ch;
}
.up{color:var(--up)}
.down{color:var(--down)}

@media print{
  :root{--paper:#fff;--card:#f2f2f2;--ink:#000;--ink-soft:#444;--rule:#bbb}
  .wrap{padding:0}
  h2{page-break-after:avoid}
  tr{page-break-inside:avoid}
}
</style>
</head>
<body>
<div class="wrap">
  <!-- sections go here, in the order given below for your report mode -->
</div>
</body>
</html>
```

## The masthead and the hero bar — both modes, always first

```html
<h1 class="title"><game title, copied character for character from the GAME: line></h1>
<p class="sub"><N> reviews sampled, <first date> to <last date> · appid <N></p>

<div class="hero">
  <div class="bar" role="img" aria-label="<N> positive, <N> negative">
    <span class="b-up" style="flex:<up count>">▲ <up count></span>
    <span class="b-down" style="flex:<down count>"><down count> ▼</span>
  </div>
  <div class="hero-read">
    <span>…</span><span>…</span><span>…</span>
  </div>
</div>
```

`flex:` on each half is the **raw review count**, not a percentage — the browser does the
division, so the bar cannot disagree with the numbers printed inside it. If one side is 0,
drop its `<span>` entirely rather than leaving a zero-width sliver with a label in it.

`.hero-read` holds two or three short readings, each in its own `<span>`, with the figure in
`<b>`. In **Advanced** those are the sample's positive rate, the NOW window's rate and size,
and the substantive count named as the denominator the rest of the page uses. In **Simplified**
they are counts only — that mode allows no percentages anywhere, and that rule outranks this
skeleton, so use ▲/▼ counts and the sample size instead.

**`<p class="warn">` — only when there is something to warn about.** This is where the TIMELINE
warnings land: a sample that spans too few days to be a history, a NOW window too short to call
a trend, a widened or narrowed window, a trend flagged NOISY. One short paragraph, immediately
after the hero, in plain words. **If TIMELINE raises none of them, omit the element** — an
empty warning strip on a clean sample teaches the reader to ignore the real one.

## Advanced mode — the sections, in this order

Each is an `<h2>` followed by its content. Every table goes inside `<div class="scroll">` so a
narrow screen scrolls the table instead of the page — the one exception is Snapshot, which
gets `<div class="snapshot">` instead.

1. **Snapshot** — `<div class="snapshot"><table><tbody>`, one `<tr>` per row of the Snapshot
   table in the instructions, `<th>` for the field name and `<td>` for the value. No `<thead>`.
   Wrap a "now" or a bad direction in `<span class="down">`, a good one in `<span class="up">`,
   and nothing else in colour.
2. **Who it's for** — `<div class="forwho">` with exactly two children:
   `<div class="buy"><h3>Buy it if you</h3><p>…</p></div>` and
   `<div class="skip"><h3>Skip it if you</h3><p>…</p></div>`. Semicolon-separated clauses,
   same caps as above.
3. **Loved vs hated** — four columns: `Loved`, `Reviews`, `Hated`, `Reviews`. Put
   `class="n"` on both count columns, in the `<th>` and every `<td>`.
4. **Where the complaints land** — `Category`, `Reviews`, `% of substantive`. All five buckets,
   always, even at zero.
5. **Notes** — `<ul class="notes">`, one `<li>` per note, at most five.
6. **Issues** — the working, and the widest table:
   `Bucket`, `Category`, `Reviews`, `Now`, `% sub`, `Quit / stayed`, `What they say`. The
   Quit / stayed cell is the minibar:

   ```html
   <td><div class="split"><span class="minibar"><i class="m-down" style="width:61.5%"></i><i class="m-up" style="width:38.5%"></i></span><small>179 / 112</small></div></td>
   ```

   The `m-down` width is `▼ ÷ (▼ + ▲)` as a percentage to one decimal, `m-up` is the
   remainder, and the two always sum to 100. The `<small>` carries the raw counts, **▼ first**,
   as `179 / 112`. Never a percentage there — the whole point of the column is that two raw
   numbers explain themselves.
7. **`<p class="integrity">`** — the INTEGRITY line, last, no `<h2>` above it. The class draws
   its own rule. Same content as the Markdown footer: how many reviews you read, the
   denominator, and `OK` or what went wrong.

## Simplified mode — the sections, in this order

The short report has no Issues table, no bucket table and **no percentages anywhere** — the
hero bar, the `.hero-read` line and every table cell carry raw counts only.

1. **Summary** — `<h2>Summary</h2>` then `<p class="lede">`, 3–5 sentences of prose. Bold the
   two or three phrases that carry the answer with `<b>`; nothing else.
2. **Who it's for** — the same `.forwho` block as above.
3. **Best and worst** — four columns: `Best`, `Reviews`, `Worst`, `Reviews`, five rows,
   `class="n"` on the counts.
4. **What you asked about** — only when a READER FOCUS block is present. `<ul class="notes">`,
   one `<li>` per focus, the focus name in `<b>`, its review count, and one sentence.
   **Report zero as zero.**
5. **`<p class="integrity">`** — the one-line footer: how many reviews were read and how many
   carried enough text to count.

## Before you hand it over

- **The document is in the reply.** A Canvas holding the page, a file you genuinely attached, or
  one `html` block from `<!DOCTYPE html>` to `</html>`. If you cannot point at one of those in
  what you are about to send, nothing else on this list matters — and a sentence saying the file
  was created is not one of them.
- Every `<table>` is inside `.scroll` or `.snapshot`, and every count column carries `class="n"`.
- Both minibar widths on a row add up to 100, and the `<small>` next to them is ▼ then ▲.
- The hero bar's two `flex:` values are the same two numbers printed inside it.
- No `<script>`, no `src=`, no `@import`, no `http` outside a review's own quoted text.
- The `<style>` block is the sheet above, line for line and unminified, and the `<title>` reads
  `<game title> — Steam review digest`.
- The report mode's caps still hold: five Notes, ten Issues rows, five Loved/Hated rows, four
  clauses a side. A section that would be empty is omitted, not padded.
- The page left as a downloadable `.html` file named after the game — not an Artifact, not a
  code block, not a document view — with at most one sentence beside it and no copy of the
  report pasted into the chat. **On Gemini** the equivalent is the highest rung of its ladder
  that opened: a Canvas titled `<game>.html`, or the one `html` code block if Canvas would not.
- **What you handed over is HTML, not a program.** Nothing in the reply is a Python,
  JavaScript or shell snippet that writes the page, and nothing asks the reader to run
  anything. If a code tool made the file, the file is attached and the code is not shown.
- Every link in that sentence points at a file you actually created. If you could not create
  one, the sentence says so and names where the document is instead.

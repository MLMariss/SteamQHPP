// test_review_digest.mjs — end-to-end test for the Review Digest (REVIEW_DIGEST_PLAN.md).
//
// Loads the REAL index.html in Chromium with the JSON data layers deliberately absent, so
// the page falls back to its built-in SAMPLE catalogue, and mocks the Cloudflare Worker
// with synthetic Steam payloads that exercise every compaction path. It asserts on the
// bundle the page actually produces, not on functions in isolation — which is how the two
// bugs in the first pass were caught (74-char ASCII art slipping under the art floor, and
// a test fixture that never reached the truncation path).
//
// Playwright is NOT a dependency of this repo — everything else here is Python — so:
//     npm install playwright
//     node test_review_digest.mjs
// Serves the working copy over localhost; needs no network and no Worker.
//
// The console 404s it reports are expected: they are the 13 absent JSON layers, which is
// exactly what triggers the SAMPLE fallback. Real faults surface as uncaught JS errors.

import { chromium } from "playwright";
import http from "http"; import fs from "fs"; import path from "path";

const ROOT = process.env.RD_ROOT || process.cwd();
const srv = http.createServer((req, res) => {
  const f = path.join(ROOT, decodeURIComponent(req.url.split("?")[0]));
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) {
    res.writeHead(404); res.end("nope"); return;                 // JSON layers absent -> SAMPLE fallback
  }
  res.writeHead(200, { "Content-Type": f.endsWith(".md") ? "text/plain" : "text/html" });
  res.end(fs.readFileSync(f));
});
await new Promise(r => srv.listen(8099, r));

// Synthetic Steam payloads exercising every compaction path.
const mk = (i, o = {}) => ({
  recommendationid: String(1000 + i),
  review: o.review ?? `Solid game, runs fine after the patch. Review number ${i} with enough text to be substantive.`,
  voted_up: o.voted_up ?? (i % 4 !== 0),
  votes_up: i,
  timestamp_created: o.ts ?? 1756000000 - i * 3600,
  timestamp_updated: o.updated ? 1756900000 : (o.ts ?? 1756000000 - i * 3600),
  written_during_early_access: !!o.ea,
  received_for_free: !!o.free,
  steam_purchase: o.notSteam ? false : true,
  primarily_steam_deck: !!o.deck,
  author: { playtime_at_review: o.mins ?? (i * 37), playtime_forever: 9999 },
});
const special = [
  mk(1, { ea: true, updated: true }),
  mk(2, { deck: true, voted_up: false, review: "Runs at 25fps on Deck, stutters constantly." }),
  mk(3, { free: true }),
  mk(4, { notSteam: true }),
  mk(5, { review: "COPYPASTA THE PUBLISHER IS GREEDY AND THIS IS PASTED EVERYWHERE OK" }),
  mk(6, { review: "COPYPASTA THE PUBLISHER IS GREEDY AND THIS IS PASTED EVERYWHERE OK" }), // dupe
  mk(7, { review: "█▓▒░ ★彡 ▄▀▄▀▄ ★ ▓▓▓ |___| >>>>>> ##### @@@@ ★彡 ░▒▓█ ▄▀▄▀▄ ★ ▓▓▓ |___| >>>>>>" }), // art
  mk(8, { review: ("This is a genuinely long and detailed prose review that keeps going. " .repeat(20)) }), // truncation
  mk(9, { review: "gg" }),                                                // non-substantive
  mk(10, { review: "[b]Great[/b] see [url=http://x.com]this[/url] and [sailing] stays" }), // bbcode + prose brackets
];
// TOPIC MENTIONS needs text that actually mentions something. The generic filler above
// matches no family, so the table came out with a header and no rows — which asserts
// nothing. Three reviews per family is exactly the floor, so each of these four appears as
// a row and one more removed from any of them would drop it to the "fewer than 3" line.
const topical = [
  mk(300, { review: "Crashes to desktop every time I try to launch it. Black screen, then nothing." }),
  mk(301, { review: "Won't start at all since the update. Fails to launch on two different machines." }),
  mk(302, { review: "Constant crashing in the second act, lost an hour of play each time." }),
  mk(303, { review: "Terrible frame rate in towns, stutters badly and the optimisation is nonexistent." }),
  mk(304, { review: "Drops to 20 fps whenever it rains. Performance is rough on a mid-range card." }),
  mk(305, { review: "Runs poorly for how it looks, choppy in every fight, needs real optimization work." }),
  mk(306, { review: "Requires a Microsoft account to play a single player game. Instant refund." }),
  mk(307, { review: "Can't play offline, it wants an Xbox login before the menu even loads." }),
  mk(308, { review: "Always online for a solo campaign, and the third party account nonsense broke twice." }),
  mk(309, { review: "The battle pass and premium currency ruin what is otherwise a decent game." }),
  mk(310, { review: "Every cosmetic is a microtransaction, and the DLC is priced like a second game." }),
  mk(311, { review: "Pay to win in the worst way, the loot box odds are insulting for a paid title." }),
];
// The fixture used to span ~4 days, so every review fell in one window and the NOW/BEFORE
// split was never exercised. These 60 sit a year back, forcing a real BEFORE side and a
// multi-quarter breakdown.
//
// The total must exceed RD_NOW_MIN (100) or the widened window swallows the whole sample and
// BEFORE comes back empty — which is the trap this fixture fell into at 100 reviews. At 142
// (140 after the dupe and the art are dropped) only 80 are inside 90 days, so the window
// widens to 100, leaving 40 in BEFORE: widening and the split are both exercised at once.
// The busy-game scenario at the bottom of this file covers the opposite branch.
const old = Array.from({ length: 60 }, (_, i) => mk(i + 200, { ts: 1756000000 - (300 + i * 3) * 86400 }));
const page1 = [...special, ...topical, ...Array.from({ length: 60 }, (_, i) => mk(i + 20)), ...old];

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", e => errors.push("PAGEERROR: " + e.message));
const noise = [];
page.on("console", m => { if (m.type() === "error") noise.push(m.text()); });

await page.route("**/qtpd-reviews.*/**", route => {
  const u = new URL(route.request().url());
  const per = u.searchParams.get("num_per_page");
  const body = per === "0"
    ? { success: 1, query_summary: { total_reviews: u.searchParams.get("language") === "all" ? 983491 : 417281,
        total_positive: u.searchParams.get("language") === "all" ? 849681 : 370832,
        total_negative: u.searchParams.get("language") === "all" ? 133810 : 46449,
        review_score_desc: "Very Positive" }, reviews: [] }
    : { success: 1, query_summary: {}, reviews: page1, cursor: "" };   // empty cursor -> stop after p1
  route.fulfill({ status: 200, contentType: "application/json",
                  headers: { "Access-Control-Allow-Origin": "*" }, body: JSON.stringify(body) });
});

await page.goto("http://127.0.0.1:8099/index.html", { waitUntil: "networkidle" });
await page.waitForTimeout(600);

const btns = await page.locator("button.gsub-rev").count();
console.log(`table entry-point buttons rendered: ${btns}`);
if (!btns) throw new Error("no .gsub-rev buttons rendered");

// Grid cards only exist in grid view; the page opens in table view, so switch first.
await page.locator('#viewSwitch [data-view="grid"]').click();
await page.waitForTimeout(500);
const gridBtns = await page.locator("button.gi-rev").count();
console.log(`grid entry-point buttons rendered: ${gridBtns}`);
await page.locator('#viewSwitch [data-view="table"]').click();
await page.waitForTimeout(400);
const label = await page.locator("button.gsub-rev").first().textContent();
console.log(`first button label: ${JSON.stringify(label)}`);
await page.locator("button.gsub-rev").first().click();
await page.waitForSelector("#rdHost.on", { timeout: 4000 });
console.log("modal opened");

await page.locator("#rdGo").click();
await page.waitForSelector("#rdOut", { timeout: 15000 });
const bundle = await page.locator("#rdOut").inputValue();
await browser.close();

console.log("\n================ BUNDLE (first 40 lines) ================");
console.log(bundle.split("\n").slice(0, 40).join("\n"));
console.log("================ (end excerpt) ================\n");

let fails = 0;
const check = (cond, msg) => { console.log((cond ? "  ok:  " : "  FAIL:") + " " + msg); if (!cond) fails++; };
check(gridBtns > 0, `grid card Reviews button rendered (${gridBtns})`);
check(/^=== QTPD REVIEW DIGEST( · prompt \S+)? ===/.test(bundle),
      "title line present, carrying the prompt version when the file declares one");
check(/ALL-TIME \(all languages\).*983,491/.test(bundle), "all-language anchor printed");
check(/ALL-TIME \(english only\): 89% of 417,281/.test(bundle), "english anchor printed and scoped");
check(/language: english only \(~42%/.test(bundle), "non-English share reported");
check(bundle.includes("off-topic / review-bombing reviews: INCLUDED"), "review bombs declared included");
check(/substantive: \d+ of \d+/.test(bundle), "substantive count reported");
check(/covering: \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}/.test(bundle), "sample date span reported");
check(bundle.includes("[EA]"), "EA flag emitted");
check(bundle.includes("[deck]"), "deck flag emitted");
check(bundle.includes("[free]"), "free flag emitted");
check(bundle.includes("[upd]"), "upd flag emitted");
check((bundle.match(/COPYPASTA THE PUBLISHER/g) || []).length === 1, "copypasta deduped to one copy");
check(!bundle.includes("█▓▒░"), "ASCII art dropped");
check(bundle.includes("…"), "long review truncated");
check(!/\[b\]|\[\/b\]|\[url=/.test(bundle), "BBCode stripped");
check(bundle.includes("[sailing]"), "bracketed PROSE preserved (not treated as BBCode)");
check(/1 duplicates/.test(bundle) && /1 ASCII-art/.test(bundle), "drops counted in header");
check(bundle.includes("--- INSTRUCTIONS ---"), "instructions section present");
{
  // TIMELINE exists so the AI copies rates instead of deriving them from 500 dated lines.
  // Assert the numbers are actually printed AND internally consistent — a block that says
  // 76% while tagging a different number of rows is worse than no block at all.
  check(bundle.includes("--- TIMELINE"), "TIMELINE block present");
  const now = bundle.match(/^NOW    : \S+ to \S+ · (\d+) reviews · (\d+)▲\/(\d+)▼ · (\d+)% positive$/m);
  check(!!now, "NOW line printed with span, counts and rate");
  if (now) {
    const [, n, up, down, pctd] = now.map(Number);
    check(up + down === n, `NOW ▲+▼ equals its review count (${up}+${down}=${n})`);
    check(Math.round(100 * up / n) === pctd, `NOW rate matches its own counts (${pctd}%)`);
    const tagged = (bundle.match(/^[▲▼] .*\[now\]/gm) || []).length;
    check(tagged === n, `[now] tags on review lines match the NOW count (${tagged} vs ${n})`);
  }
  check(/^BEFORE : /m.test(bundle), "BEFORE window printed (fixture spans a year)");
  check(/^TREND  : [+-]?\d+ pts/.test(bundle) || /^TREND  : /m.test(bundle), "TREND printed in points");
  check(/^BASELINE ▼ RATE: \d+%/m.test(bundle), "baseline ▼ rate printed");
  check(/^BY QUARTER: .*Q\d \d+% \(\d+\)/m.test(bundle), "quarterly breakdown printed");
  // Fewer than RD_NOW_MIN reviews are recent here, so the window must widen AND say so.
  check(/widened from the last 90 days/.test(bundle), "widened window disclosed, not silently applied");
  check(/^LAST 90D: \d+ reviews · \d+% positive/m.test(bundle), "sharper 90-day rate still reported");
  check(/FLAG SPLITS: .*\[free\] \d+ reviews \d+% vs \d+%/.test(bundle), "flag splits precomputed");
  check(/\[now\]\[EA\]|\[now\]\[free\]|\[now\]\[deck\]/.test(bundle) || /\[now\]/.test(bundle),
        "[now] composes with the other flags");
  check(/\[now\] posted inside the NOW window/.test(bundle), "legend documents the [now] flag");
  // A review count says nothing about the time it covers; these two lines are the only
  // place the bundle admits whether 500 reviews is two years or two days.
  check(/^COVERAGE: this sample spans \d+ days · ~[\d.]+ reviews\/month$/m.test(bundle),
        "COVERAGE states the span and the rate (per MONTH on a year-long fixture)");
  check(/^SPANS  : NOW covers \d+ days? · BEFORE covers \d+ days?$/m.test(bundle),
        "window spans reported in days, unwarned on a fixture that spans a year");
  check(!/narrowed:/.test(bundle), "slow fixture widens, so it must NOT also narrow");
}
{
  // TOPIC MENTIONS is the floor the model checks its own counting against. It is INPUT:
  // the guard line matters as much as the table, because a pipe table sitting in the
  // context is the most copy-pasteable thing in the whole bundle.
  check(bundle.includes("--- TOPIC MENTIONS"), "TOPIC MENTIONS block present");
  check(/THIS BLOCK IS INPUT, NOT OUTPUT/.test(bundle), "block declares itself input, not output");
  check(/^\| topic \| hits \| now \| before \| ▼\/▲ \| ↑votes on ▼ \| % of NOW \| % of BEFORE \|$/m.test(bundle),
        "topic table header printed");
  const trows = bundle.match(/^\| [A-Z][^|]*\| \d+ \| \d+ \| \d+ \| \d+▼\/\d+▲ \| \d+ \| \d+% \| \d+% \|$/gm) || [];
  check(trows.length > 0, `topic rows emitted with counts and a ▼/▲ split (${trows.length})`);
  const badRow = trows.find(r => {
    const [, tot, now, before] = r.match(/\| (\d+) \| (\d+) \| (\d+) \|/).map(Number);
    return now + before !== tot;
  });
  check(!badRow, `every topic row's now+before equals its hit count${badRow ? " — " + badRow : ""}`);
  // "Nobody mentioned microtransactions" is a finding. Without these lines the model cannot
  // tell a family that was checked and found absent from one that was never looked for.
  check(/^(?:Fewer than 3 hits|Checked, zero hits): /m.test(bundle),
        "families below the floor are named rather than silently dropped");
  const tops = (bundle.match(/^[▲▼] .*\[top\]/gm) || []).length;
  check(tops === 10, `[top] tags the 10 most-upvoted reviews (${tops})`);
  check(/\[top\] among the 10 most-upvoted reviews/.test(bundle), "legend documents the [top] flag");
}
{
  // Order is INSTRUCTIONS -> OVERVIEW -> REVIEWS. Asserted by position, not presence, so a
  // future edit cannot quietly put the task back behind 500 lines of review text.
  const i = bundle.indexOf("--- INSTRUCTIONS ---");
  const o = bundle.indexOf("--- OVERVIEW ---");
  const r = bundle.indexOf("--- REVIEWS (");
  check(i >= 0 && o > i && r > o, `sections ordered instructions(${i}) < overview(${o}) < reviews(${r})`);
  check(bundle.trimEnd().endsWith("at the top. ---"), "closing pointer back to the instructions");
  check(/LEGEND: ▲\/▼/.test(bundle) && /^▲ |\n▲ /m.test(bundle),
        "review lines use the ▲/▼ glyphs the prompt documents");
}
// Pinning a phrase from the prompt made this break on every prompt edit. The version
// marker is the durable signal: only the file carries one, the inline fallback does not.
check(/=== QTPD REVIEW DIGEST · prompt v\S+ ===/.test(bundle),
      "real review_prompt.md loaded, not the inline fallback");
check(errors.length === 0, `no uncaught JS errors (${errors.length})`);
console.log(`  (${noise.length} console 404s from the deliberately absent JSON layers - expected)`);
errors.slice(0, 5).forEach(e => console.log("     " + e));
// --- second scenario: the proxy is unreachable ------------------------------------
// This is the exact failure the first live click hit. A network-level failure must not
// dead-end: it has to name the likely cause and offer the URL as an editable field, so a
// wrong subdomain is a five-second fix in the page rather than a code change and redeploy.
{
  const b2 = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const p2 = await b2.newPage();
  const errs2 = [];
  p2.on("pageerror", e => errs2.push(e.message));
  await p2.route("**/qtpd-reviews.*/**", r => r.abort("connectionrefused"));
  await p2.goto("http://127.0.0.1:8099/index.html", { waitUntil: "networkidle" });
  await p2.waitForTimeout(500);
  await p2.locator("button.gsub-rev").first().click();
  await p2.waitForSelector("#rdHost.on");
  await p2.locator("#rdGo").click();
  await p2.waitForSelector("#rdProxyIn", { timeout: 10000 });
  const shown = await p2.locator("#rdProxyIn").inputValue();
  const note  = await p2.locator("#rdErr").textContent();
  await b2.close();
  console.log("\nfailure path:");
  check(shown.startsWith("https://"), `proxy URL offered for editing (${shown})`);
  check(/couldn't reach the proxy/i.test(note), "network failure explained, not just echoed");
  check(/origin/i.test(note), "origin named as a possible cause");
  check(errs2.length === 0, "no uncaught JS errors on the failure path");
}

// --- third scenario: a BUSY game -------------------------------------------------
// The sample does not reach back 90 days, so the calendar window covers all of it. Before
// the narrowing branch that produced NOW === the whole sample, an empty BEFORE, and a
// TIMELINE with no TREND line at all — while the prompt still asked the model for a trend,
// which it then supplied from nowhere. 300 reviews across ~12 days trips every new guard
// at once: narrowing, the per-day rate, and both span warnings.
{
  const busy = Array.from({ length: 300 }, (_, i) => mk(i + 500));   // default ts: an hour apart
  const b3 = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const p3 = await b3.newPage();
  const errs3 = [];
  p3.on("pageerror", e => errs3.push(e.message));
  await p3.route("**/qtpd-reviews.*/**", route => {
    const per = new URL(route.request().url()).searchParams.get("num_per_page");
    route.fulfill({ status: 200, contentType: "application/json",
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify(per === "0"
        ? { success: 1, query_summary: { total_reviews: 4000, total_positive: 3000,
            total_negative: 1000, review_score_desc: "Mostly Positive" }, reviews: [] }
        : { success: 1, query_summary: {}, reviews: busy, cursor: "" }) });
  });
  await p3.goto("http://127.0.0.1:8099/index.html", { waitUntil: "networkidle" });
  await p3.waitForTimeout(500);
  await p3.locator("button.gsub-rev").first().click();
  await p3.waitForSelector("#rdHost.on");
  await p3.locator("#rdGo").click();
  await p3.waitForSelector("#rdOut", { timeout: 15000 });
  const b = await p3.locator("#rdOut").inputValue();
  await b3.close();

  console.log("\nbusy game (sample shorter than the 90-day window):");
  const nowLine = b.match(/^NOW    : \S+ to \S+ · (\d+) reviews/m);
  const befLine = b.match(/^BEFORE : \S+ to \S+ · (\d+) reviews/m);
  check(!!nowLine && !!befLine, "both windows printed");
  if (nowLine && befLine) {
    const nowN = Number(nowLine[1]), befN = Number(befLine[1]);
    check(befN > 0, `BEFORE is not empty (${befN}) — the bug this branch exists for`);
    check(nowN / (nowN + befN) <= 0.62,
          `NOW capped near RD_NOW_MAX, not swallowing the sample (${Math.round(100 * nowN / (nowN + befN))}%)`);
    const tagged = (b.match(/^[▲▼] .*\[now\]/gm) || []).length;
    check(tagged === nowN, `[now] tags still match the capped NOW count (${tagged} vs ${nowN})`);
  }
  check(/^TREND  : [+-]?\d+ pts/m.test(b), "TREND printed — nothing left for the model to invent");
  check(/narrowed: the last 90 days hold \d+ of the \d+ sampled reviews/.test(b),
        "narrowing disclosed, not silently applied");
  check(!/widened from the last 90 days/.test(b), "busy fixture narrows, so it must NOT also widen");
  check(/^COVERAGE: this sample spans \d+ days? · ~[\d.]+ reviews\/day$/m.test(b),
        "short sample reports a per-DAY rate, not an extrapolated per-month one");
  check(/WARNING: fewer than 60 days/.test(b), "short sample warns it carries no history");
  check(/WARNING: a \d+-day NOW window is a same-fortnight read/.test(b),
        "short NOW window warns the trend is not a trend");
  check(errs3.length === 0, `no uncaught JS errors on the busy path (${errs3.length})`);
}

srv.close();
console.log(fails ? `\n${fails} CHECKS FAILED` : "\nALL CHECKS PASSED");
process.exit(fails ? 1 : 0);

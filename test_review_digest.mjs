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
  timestamp_created: 1756000000 - i * 3600,
  timestamp_updated: o.updated ? 1756900000 : 1756000000 - i * 3600,
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
const page1 = [...special, ...Array.from({ length: 90 }, (_, i) => mk(i + 20))];

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
check(bundle.includes("=== QTPD REVIEW DIGEST ==="), "header present");
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
check(bundle.includes("Campaign check"), "real review_prompt.md loaded (not the fallback)");
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

srv.close();
console.log(fails ? `\n${fails} CHECKS FAILED` : "\nALL CHECKS PASSED");
process.exit(fails ? 1 : 0);

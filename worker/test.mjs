// Unit tests for the parts of the Worker that hold regardless of runtime: the appid
// validation and the parameter allowlist. These are what stop it being an open proxy, so
// they are the parts worth testing. Run: node worker/test.mjs
import { buildUpstreamUrl, corsHeaders } from "./index.js";

let fail = 0;
const ok = (cond, msg) => { if (!cond) { console.error("  FAIL:", msg); fail++; } else console.log("  ok:", msg); };
const build = (qs) => buildUpstreamUrl(new URL("https://w.dev/?" + qs).searchParams);

console.log("appid validation");
ok(build("appid=570").url === "https://store.steampowered.com/appreviews/570?json=1", "plain appid builds the upstream URL");
ok(build("").error, "missing appid rejected");
ok(build("appid=").error, "empty appid rejected");
ok(build("appid=abc").error, "non-numeric appid rejected");
ok(build("appid=570/../../search").error, "path traversal rejected");
ok(build("appid=-1").error, "negative appid rejected");
ok(build("appid=999999999").error, "9-digit appid rejected (out of range)");
ok(build("appid=570%20").error, "trailing space rejected");

console.log("param allowlist");
{
  const u = new URL(build("appid=570&filter=recent&language=english&filter_offtopic_activity=0").url);
  ok(u.searchParams.get("filter") === "recent", "filter forwarded");
  ok(u.searchParams.get("language") === "english", "language forwarded");
  ok(u.searchParams.get("filter_offtopic_activity") === "0", "offtopic flag forwarded");
  ok(u.searchParams.get("json") === "1", "json=1 always set");
}
{
  const u = new URL(build("appid=570&evil=1&redirect=http://x&key=secret&json=0").url);
  ok(!u.searchParams.has("evil"), "unknown param dropped");
  ok(!u.searchParams.has("redirect"), "redirect param dropped");
  ok(!u.searchParams.has("key"), "key param dropped");
  ok(u.searchParams.get("json") === "1", "caller cannot override json=1");
}

console.log("num_per_page clamping");
ok(new URL(build("appid=570&num_per_page=5000").url).searchParams.get("num_per_page") === "100", "over-max clamped to 100");
ok(new URL(build("appid=570&num_per_page=50").url).searchParams.get("num_per_page") === "50", "in-range preserved");
ok(new URL(build("appid=570&num_per_page=0").url).searchParams.get("num_per_page") === "0", "zero PRESERVED - it means summary-only, the header's cheap anchor call");
ok(new URL(build("appid=570&num_per_page=-5").url).searchParams.get("num_per_page") === "0", "negative clamped to 0");
ok(new URL(build("appid=570&num_per_page=junk").url).searchParams.get("num_per_page") === "100", "garbage falls back to 100");

console.log("CORS origin allowlist");
ok(corsHeaders("https://mlmariss.github.io")["Access-Control-Allow-Origin"] === "https://mlmariss.github.io", "pages origin allowed");
ok(corsHeaders("https://evil.example") === null, "unknown origin refused");
ok(corsHeaders(null) === null, "absent origin yields no CORS headers");
ok(corsHeaders("https://mlmariss.github.io").Vary === "Origin", "Vary: Origin set");

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);

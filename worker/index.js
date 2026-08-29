/**
 * qtpd-reviews — Cloudflare Worker passthrough for Steam's `appreviews` endpoint.
 *
 * WHY THIS EXISTS
 * ---------------
 * The Phase 0 probe (REVIEW_DIGEST_PLAN.md §14) established that
 * `store.steampowered.com/appreviews/` returns **no** `Access-Control-Allow-Origin`
 * header, so a page on GitHub Pages cannot call it directly. QTPD is static — there is no
 * application server — so the only way to reach Steam from the browser is a proxy. This is
 * that proxy, and it is the sole backend the Review Digest needs.
 *
 * ITS SOURCE LIVES IN THE REPO ON PURPOSE. The older wishlist Worker
 * (qhpp-wishlist.mlmariss.workers.dev) was deployed without its source in git, and it is
 * now unrecoverable — which is the entire reason this feature was expensive to scope. Do
 * not repeat that: edit this file, redeploy from it, keep them in sync.
 *
 * WHAT IT DELIBERATELY IS NOT
 * ---------------------------
 * Not a general-purpose proxy. It forwards exactly one upstream path shape with exactly one
 * allowlisted parameter set. Without those two constraints anyone who found the URL would
 * have an open relay to Steam's whole domain running on someone else's Cloudflare account.
 *
 * DEPLOY: see worker/README.md
 */

// The browser origins allowed to use this Worker. NOT "*" — an open CORS policy on an
// open-ish proxy is how a hobby Worker becomes someone else's free infrastructure.
// GitHub Pages project sites are served from the user origin, so the path
// (/SteamQTPD/) is not part of the origin and must not appear here.
const ALLOWED_ORIGINS = new Set([
  "https://mlmariss.github.io",
  "http://localhost:8000",       // local `python -m http.server` while developing
  "http://127.0.0.1:8000",
]);

// Exactly the parameters REVIEW_DIGEST_PLAN.md §4 uses. Anything else the caller sends is
// dropped rather than forwarded — an allowlist, never a denylist.
const ALLOWED_PARAMS = new Set([
  "filter",                    // recent | updated | all
  "language",                  // english | all | ...
  "review_type",               // all | positive | negative
  "purchase_type",             // all | steam | non_steam_purchase
  "num_per_page",              // clamped to 100 below (Steam's own hard max)
  "cursor",                    // "*" then whatever Steam echoes back
  "day_range",                 // only meaningful with filter=all
  "filter_offtopic_activity",  // 0 includes review bombs — QTPD sends 0 (plan §5)
]);

// Steam's numbers barely move in half an hour, and a digest is often re-opened moments
// after it is closed. Caching also keeps this Worker's shared egress IP well clear of the
// storefront rate limiter, which matters far more here than it does for the scrapers
// (they get a fresh runner IP; every user of this Worker shares one pool).
const CACHE_SECONDS = 1800;

// Mirrors the cookies the repo's Python scrapers send, so mature-gated titles return
// reviews instead of an age-check interstitial.
const UPSTREAM_HEADERS = {
  "User-Agent": "Mozilla/5.0 (steam-qtpd review-digest; +https://github.com/MLMariss/SteamQTPD)",
  "Accept-Language": "en-US,en;q=0.9",
  "Cookie": "birthtime=568022401; mature_content=1; Steam_Language=english; wants_mature_content=1",
};

/** CORS headers for a request, or null when the origin is not allowed. */
export function corsHeaders(origin) {
  if (!origin || !ALLOWED_ORIGINS.has(origin)) return null;
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Max-Age": "86400",
    // The allowed origin varies per request, so caches must key on it.
    "Vary": "Origin",
  };
}

/**
 * Build the upstream Steam URL from a caller's params.
 * Exported so the allowlist and the appid validation are unit-testable without a runtime.
 * Returns {url} or {error, status}.
 */
export function buildUpstreamUrl(searchParams) {
  const appid = searchParams.get("appid");
  // Steam appids are plain integers. Anchored, digits only, bounded — this is what stops
  // the Worker being pointed at an arbitrary path on store.steampowered.com.
  if (!appid || !/^[0-9]{1,8}$/.test(appid)) {
    return { error: "appid must be 1-8 digits", status: 400 };
  }

  const out = new URL(`https://store.steampowered.com/appreviews/${appid}`);
  out.searchParams.set("json", "1");        // always; never taken from the caller

  for (const [key, value] of searchParams) {
    if (!ALLOWED_PARAMS.has(key)) continue;  // silently dropped, not an error
    if (key === "num_per_page") {
      // Steam's hard max is 100; clamp rather than reject so a caller asking for more gets
      // a page instead of a failure. ZERO IS LEGITIMATE and must survive: num_per_page=0
      // returns query_summary with no review bodies, which is how the bundle header gets
      // its population anchor for one cheap call (scraper.py:rating_from_reviews and
      // review_probe.py both rely on it). An earlier `|| 100` fallback silently turned that
      // into a full page fetch, so NaN is distinguished from 0 explicitly.
      const parsed = parseInt(value, 10);
      const n = Number.isNaN(parsed) ? 100 : Math.min(100, Math.max(0, parsed));
      out.searchParams.set(key, String(n));
      continue;
    }
    out.searchParams.set(key, value);
  }
  return { url: out.toString() };
}

function json(body, status, extraHeaders) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...(extraHeaders || {}) },
  });
}

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin");
    const cors = corsHeaders(origin);

    if (request.method === "OPTIONS") {
      // A plain GET with no custom headers is a "simple request" and browsers will not
      // preflight it — but answer correctly anyway rather than 405 a legitimate probe.
      return cors
        ? new Response(null, { status: 204, headers: cors })
        : new Response(null, { status: 403 });
    }

    if (request.method !== "GET") {
      return json({ error: "method not allowed" }, 405, cors || {});
    }

    // A browser request from an origin we do not serve is refused. Note this is a
    // courtesy boundary, not a security one: Origin is only sent by browsers and anything
    // else can omit or forge it. The real protections are the appid regex and the param
    // allowlist above, which hold regardless of who is calling.
    if (origin && !cors) {
      return json({ error: "origin not allowed" }, 403);
    }

    const url = new URL(request.url);
    if (!url.searchParams.has("appid")) {
      return json({
        service: "qtpd-reviews",
        usage: "/?appid=<steam appid>&filter=recent&language=english&num_per_page=100&cursor=*",
        source: "https://github.com/MLMariss/SteamQTPD/tree/main/worker",
      }, 200, cors || {});
    }

    const built = buildUpstreamUrl(url.searchParams);
    if (built.error) return json({ error: built.error }, built.status, cors || {});

    // Cache on the normalised upstream URL, so two callers who ordered their query string
    // differently still share one entry.
    const cacheKey = new Request(built.url, { method: "GET" });
    const cache = caches.default;

    let upstream = await cache.match(cacheKey);
    let cacheStatus = "HIT";

    if (!upstream) {
      cacheStatus = "MISS";
      let fetched;
      try {
        fetched = await fetch(built.url, { headers: UPSTREAM_HEADERS });
      } catch (e) {
        return json({ error: "upstream fetch failed", detail: String(e) }, 502, cors || {});
      }

      if (!fetched.ok) {
        // Pass the real status through (429 and 403 are the ones that matter) but do NOT
        // cache a failure — the next caller should get a fresh attempt.
        return json({ error: "upstream error", status: fetched.status },
                    fetched.status === 429 ? 429 : 502, cors || {});
      }

      // Rebuild the response rather than forwarding Steam's: its Set-Cookie (browserid,
      // steamCountry) is useless to the page, would be stored against this Worker's own
      // domain, and must never be written into the shared cache.
      const body = await fetched.text();
      upstream = new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
        },
      });
      // Cache the CORS-free copy; the per-origin headers are added on the way out below.
      ctx.waitUntil(cache.put(cacheKey, upstream.clone()));
    }

    const headers = new Headers(upstream.headers);
    for (const [k, v] of Object.entries(cors || {})) headers.set(k, v);
    headers.set("X-QTPD-Cache", cacheStatus);
    return new Response(upstream.body, { status: 200, headers });
  },
};

/**
 * `frontend/vercel.json` as data.
 *
 * Nothing else in CI exercises this file: the e2e suite serves the built
 * `dist/` with `vite preview` on localhost, so Vercel's own rewrite/header
 * engine never runs against it (see docs/DEPLOYMENT.md, "What CI does not
 * check"). That is exactly how the catch-all rewrite once answered a request
 * for a deleted asset chunk with `200 text/html` instead of a 404 — a
 * stale-chunk failure that surfaced as
 * `'text/html' is not a valid JavaScript MIME type` instead of the recovery
 * path in `ErrorBoundary.tsx` / `lazyRoute.ts` ever getting a chance to run.
 *
 * `source` strings here aren't plain paths — `:path*` and `(.*)` are
 * path-to-regexp syntax, the same library Vercel's own routing engine
 * (`@vercel/routing-utils`) compiles them with. Asserting on the JSON
 * shape (e.g. "the catch-all source string contains 'assets'") would pass
 * for a subtly wrong pattern that still happens to mention the word. This
 * test instead compiles each `source` into the actual RegExp Vercel would
 * use and runs real request paths through it, so a regression in the
 * pattern itself — not just its text — fails the test.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { pathToRegexp, type Key } from "path-to-regexp";

const VERCEL_JSON_PATH = join(import.meta.dirname, "..", "..", "vercel.json");

interface RewriteRule {
  source: string;
  destination: string;
}

interface HeaderEntry {
  key: string;
  value: string;
}

interface HeaderRule {
  source: string;
  headers: HeaderEntry[];
}

interface VercelConfig {
  rewrites: RewriteRule[];
  headers: HeaderRule[];
}

function readVercelConfig(): VercelConfig {
  return JSON.parse(readFileSync(VERCEL_JSON_PATH, "utf-8")) as VercelConfig;
}

/**
 * Compiles a `vercel.json` "source" string into the RegExp Vercel's own
 * `@vercel/routing-utils` would match a request path against —
 * `sourceToRegex()` in that package calls `pathToRegexp` with exactly these
 * options (`strict`/`sensitive`/`delimiter: "/"`), on the same major version
 * (`path-to-regexp@6.x`) Vercel pins as its "current" compiler.
 */
function compileSource(source: string): RegExp {
  const keys: Key[] = []
  return pathToRegexp(source, keys, { strict: true, sensitive: true, delimiter: "/" })
}

describe("frontend/vercel.json", () => {
  const config = readVercelConfig();

  describe("catch-all SPA rewrite", () => {
    // Identified by behavior (rewrites to the SPA shell), not by index —
    // a reordering of the array shouldn't silently start testing the wrong
    // rule.
    const catchAll = config.rewrites.find((r) => r.destination === "/index.html");

    it("exists", () => {
      expect(catchAll).toBeDefined();
    });

    const regex = compileSource(catchAll!.source);

    it.each(["/", "/courses", "/courses/abc", "/invite/accept"])(
      "rewrites app route %s to the SPA shell",
      (path) => {
        expect(regex.test(path)).toBe(true);
      },
    );

    it.each(["/assets/index-ABC12345.js", "/assets/nope.css"])(
      "does NOT rewrite a hashed asset request (%s) — that must 404, not fall back to index.html",
      (path) => {
        expect(regex.test(path)).toBe(false);
      },
    );
  });

  describe("Supabase storage proxy rewrites run before the catch-all", () => {
    const catchAllIndex = config.rewrites.findIndex((r) => r.destination === "/index.html");
    const courseAssetsIndex = config.rewrites.findIndex((r) =>
      r.destination.includes("/course-assets/"),
    );
    const avatarsIndex = config.rewrites.findIndex((r) => r.destination.includes("/avatars/"));

    it("all three rules are present", () => {
      expect(catchAllIndex).toBeGreaterThanOrEqual(0);
      expect(courseAssetsIndex).toBeGreaterThanOrEqual(0);
      expect(avatarsIndex).toBeGreaterThanOrEqual(0);
    });

    // Vercel evaluates `rewrites` in array order and stops at the first
    // match. The catch-all's own pattern already excludes `/assets/` (the
    // hashed JS bundles), but nothing about its regex excludes `/img/...` —
    // only being listed AFTER these two keeps the image proxy reachable.
    it("/img/course-assets/:path* is listed before the catch-all", () => {
      expect(courseAssetsIndex).toBeLessThan(catchAllIndex);
    });

    it("/img/avatars/:path* is listed before the catch-all", () => {
      expect(avatarsIndex).toBeLessThan(catchAllIndex);
    });

    it("both proxy rules still match the paths they're meant for", () => {
      expect(compileSource(config.rewrites[courseAssetsIndex].source).test(
        "/img/course-assets/lesson-1/cover.jpg",
      )).toBe(true);
      expect(compileSource(config.rewrites[avatarsIndex].source).test(
        "/img/avatars/user-123.png",
      )).toBe(true);
    });
  });

  describe("/assets/ cache headers", () => {
    // Identified by which requests it actually matches, not by re-typing
    // the source string — a rule that matched the wrong prefix but still
    // had "assets" in its source would slip past a string-equality check.
    const assetsRule = config.headers.find((h) =>
      compileSource(h.source).test("/assets/index-ABC12345.js"),
    );

    it("exists and applies to hashed asset requests", () => {
      expect(assetsRule).toBeDefined();
    });

    it("does not also apply to an ordinary app route", () => {
      expect(compileSource(assetsRule!.source).test("/courses")).toBe(false);
    });

    it("sets an immutable, long-lived Cache-Control", () => {
      const cacheControl = assetsRule!.headers.find((h) => h.key === "Cache-Control");
      expect(cacheControl).toBeDefined();
      expect(cacheControl!.value).toMatch(/\bimmutable\b/);

      const maxAgeMatch = cacheControl!.value.match(/max-age=(\d+)/);
      expect(maxAgeMatch).not.toBeNull();
      // Vite content-hashes every asset filename, so a cached copy is safe
      // to keep for as long as a browser cares to — a full year is the de
      // facto ceiling browsers respect. Anything much shorter defeats the
      // point of hashed filenames; asset requests would keep revalidating
      // even though the content at that exact URL can never change.
      const ONE_YEAR_SECONDS = 31_536_000;
      expect(Number(maxAgeMatch![1])).toBeGreaterThanOrEqual(ONE_YEAR_SECONDS);
    });
  });

  describe("security headers", () => {
    const generalRule = config.headers.find((h) => compileSource(h.source).test("/courses"));

    it("exists and applies to ordinary app routes", () => {
      expect(generalRule).toBeDefined();
    });

    it("sets a Content-Security-Policy that denies framing", () => {
      const csp = generalRule!.headers.find((h) => h.key === "Content-Security-Policy");
      expect(csp).toBeDefined();
      expect(csp!.value).toContain("frame-ancestors 'none'");
    });
  });
});

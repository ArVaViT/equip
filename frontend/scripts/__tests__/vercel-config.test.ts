/**
 * `frontend/vercel.json` as data.
 *
 * Nothing else in CI exercises this file: the e2e suite serves the built
 * `dist/` with `vite preview` on localhost, so Vercel's own routing engine
 * never runs against it (see docs/DEPLOYMENT.md, "What CI does not
 * check"). That is exactly how the catch-all rewrite once answered a request
 * for a deleted asset chunk with `200 text/html` instead of a 404 — a
 * stale-chunk failure that surfaced as
 * `'text/html' is not a valid JavaScript MIME type` instead of the recovery
 * path in `ErrorBoundary.tsx` / `lazyRoute.ts` ever getting a chance to run.
 *
 * The file is written in Vercel's `routes` form, not `rewrites` + `headers`.
 * The short form compiles every `headers` entry into a `continue: true`
 * route placed BEFORE the filesystem check (`getTransformedRoutes` in
 * `@vercel/routing-utils`), so a header there lands on a 404 just as much
 * as on a real file. A year of `immutable` on the 404 of a vanished chunk
 * means a browser or the CDN keeps answering "not found" for that URL long
 * after a rollback has brought the file back (2026-10-17). Only the `hit`
 * phase — routes that run when the filesystem actually served a file — can
 * tell the two apart, and only `routes` can express phases.
 *
 * Each `src` is a full regular expression (Vercel anchors it with `^…$`),
 * so these tests compile it and run real request paths through it: a
 * regression in the pattern itself — not just its text — fails the test.
 * The routes before `handle: filesystem` and the rewrites after it are the
 * exact output `@vercel/routing-utils` produced for the former short form,
 * so the move changed nothing but where the two cache rules live.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const VERCEL_JSON_PATH = join(import.meta.dirname, "..", "..", "vercel.json");

interface HandleRoute {
  handle: string;
}

interface SrcRoute {
  src: string;
  dest?: string;
  status?: number;
  headers?: Record<string, string>;
  continue?: boolean;
  check?: boolean;
}

type Route = HandleRoute | SrcRoute;

interface VercelConfig {
  routes: Route[];
  rewrites?: unknown;
  headers?: unknown;
}

function readVercelConfig(): VercelConfig {
  return JSON.parse(readFileSync(VERCEL_JSON_PATH, "utf-8")) as VercelConfig;
}

function isHandle(route: Route): route is HandleRoute {
  return "handle" in route;
}

/** The routes of one phase: everything after `handle: <name>` up to the next handle. */
function phase(routes: Route[], name: string | null): SrcRoute[] {
  const out: SrcRoute[] = [];
  let current: string | null = null;
  for (const route of routes) {
    if (isHandle(route)) {
      current = route.handle;
      continue;
    }
    if (current === name) out.push(route);
  }
  return out;
}

function matches(route: SrcRoute, path: string): boolean {
  return new RegExp(route.src).test(path);
}

describe("frontend/vercel.json", () => {
  const config = readVercelConfig();
  const main = phase(config.routes, null);
  const filesystem = phase(config.routes, "filesystem");
  const hit = phase(config.routes, "hit");

  it("uses `routes` alone — Vercel refuses `routes` mixed with `rewrites`/`headers`", () => {
    expect(config.rewrites).toBeUndefined();
    expect(config.headers).toBeUndefined();
    const handles = config.routes.filter(isHandle).map((r) => r.handle);
    expect(handles).toEqual(["filesystem", "hit"]);
  });

  it("every src is a valid, anchored regular expression", () => {
    for (const route of config.routes) {
      if (isHandle(route)) continue;
      expect(() => new RegExp(route.src)).not.toThrow();
      expect(route.src.startsWith("^")).toBe(true);
      expect(route.src.endsWith("$")).toBe(true);
    }
  });

  describe("catch-all SPA rewrite", () => {
    // Identified by behavior (rewrites to the SPA shell), not by index —
    // a reordering of the array shouldn't silently start testing the wrong
    // rule.
    const catchAll = filesystem.find((r) => r.dest === "/index.html");

    it("exists after the filesystem check", () => {
      expect(catchAll).toBeDefined();
    });

    it.each(["/", "/courses", "/courses/abc", "/invite/accept"])(
      "rewrites app route %s to the SPA shell",
      (path) => {
        expect(matches(catchAll!, path)).toBe(true);
      },
    );

    // /video/ is served with a week of `immutable`: a missing file must 404,
    // not come back as index.html cached for a week (2026-10-03).
    // Nor a /.well-known/ probe: agents and registries ask for files like
    // /.well-known/ai-catalog.json and must get a 404, not the SPA's HTML
    // passed off as an invalid manifest (Lighthouse agentic audit, 2026-10-14).
    it.each([
      "/assets/index-ABC12345.js",
      "/assets/nope.css",
      "/video/intro.mp4",
      "/video/nope.mp4",
      "/.well-known/ai-catalog.json",
      "/.well-known/nope",
    ])(
      "does NOT rewrite %s — a missing asset or /.well-known/ file must 404, not fall back to index.html",
      (path) => {
        expect(matches(catchAll!, path)).toBe(false);
      },
    );
  });

  describe("proxy rewrites run before the catch-all", () => {
    const catchAllIndex = filesystem.findIndex((r) => r.dest === "/index.html");
    const courseAssetsIndex = filesystem.findIndex((r) => r.dest?.includes("/course-assets/"));
    const avatarsIndex = filesystem.findIndex((r) => r.dest?.includes("/avatars/"));
    const logosIndex = filesystem.findIndex((r) => r.dest?.includes("/organization-logos/"));
    const intakeIndex = filesystem.findIndex((r) =>
      r.dest?.startsWith("https://browser-intake-us5-datadoghq.com/"),
    );

    it("all five rules are present", () => {
      expect(catchAllIndex).toBeGreaterThanOrEqual(0);
      expect(courseAssetsIndex).toBeGreaterThanOrEqual(0);
      expect(avatarsIndex).toBeGreaterThanOrEqual(0);
      expect(logosIndex).toBeGreaterThanOrEqual(0);
      expect(intakeIndex).toBeGreaterThanOrEqual(0);
    });

    // Vercel evaluates routes in array order and stops at the first
    // match. The catch-all's own pattern already excludes `/assets/` (the
    // hashed JS bundles), but nothing about its regex excludes `/img/...`
    // or `/_e/...` — only being listed AFTER them keeps them reachable.
    it("each proxy is listed before the catch-all", () => {
      expect(courseAssetsIndex).toBeLessThan(catchAllIndex);
      expect(avatarsIndex).toBeLessThan(catchAllIndex);
      expect(logosIndex).toBeLessThan(catchAllIndex);
      expect(intakeIndex).toBeLessThan(catchAllIndex);
    });

    it("each proxy matches the paths it is meant for and carries the path over", () => {
      const course = filesystem[courseAssetsIndex];
      const path = "/img/course-assets/lesson-1/cover.jpg";
      expect(matches(course, path)).toBe(true);
      expect(path.replace(new RegExp(course.src), course.dest!)).toBe(
        "https://rrisqutxlkamwfhcashl.supabase.co/storage/v1/object/public/course-assets/lesson-1/cover.jpg",
      );
      expect(matches(filesystem[avatarsIndex], "/img/avatars/user-123.png")).toBe(true);
      const logos = filesystem[logosIndex];
      const logo = "/img/organization-logos/b761fe38-3c83-4954-ac7c-3363a24b5d7b/logo-1a2b3c4d.png";
      expect(logo.replace(new RegExp(logos.src), logos.dest!)).toBe(
        "https://rrisqutxlkamwfhcashl.supabase.co/storage/v1/object/public/organization-logos/b761fe38-3c83-4954-ac7c-3363a24b5d7b/logo-1a2b3c4d.png",
      );
      const intake = filesystem[intakeIndex];
      expect("/_e/api/v2/rum".replace(new RegExp(intake.src), intake.dest!)).toBe(
        "https://browser-intake-us5-datadoghq.com/api/v2/rum",
      );
    });
  });

  describe("long-lived cache headers apply only to files that exist", () => {
    const allCacheRules = config.routes.filter(
      (r): r is SrcRoute => !isHandle(r) && r.headers?.["Cache-Control"] !== undefined,
    );

    // The bug: a rule before the filesystem check also stamps the 404 of a
    // vanished chunk, and `immutable` tells every cache never to ask again.
    it("no `immutable` header is set before the filesystem check", () => {
      for (const route of main) {
        expect(route.headers?.["Cache-Control"] ?? "").not.toMatch(/\bimmutable\b/);
      }
    });

    it("every `immutable` rule sits in the hit phase and only adds headers", () => {
      const immutable = allCacheRules.filter((r) => /\bimmutable\b/.test(r.headers!["Cache-Control"]));
      expect(immutable.length).toBeGreaterThan(0);
      for (const route of immutable) {
        expect(hit).toContain(route);
        // The hit phase may not redirect or change the status; Vercel
        // rejects such a route, and `continue` is mandatory there.
        expect(route.continue).toBe(true);
        expect(route.dest).toBeUndefined();
        expect(route.status).toBeUndefined();
      }
    });

    it("hashed assets get a year of `immutable`", () => {
      const assetsRule = hit.find((r) => matches(r, "/assets/index-ABC12345.js"));
      expect(assetsRule).toBeDefined();
      expect(matches(assetsRule!, "/courses")).toBe(false);
      const cacheControl = assetsRule!.headers!["Cache-Control"];
      expect(cacheControl).toMatch(/\bimmutable\b/);
      // Vite content-hashes every asset filename, so a cached copy is safe
      // to keep for as long as a browser cares to — a full year is the de
      // facto ceiling browsers respect.
      const maxAge = cacheControl.match(/max-age=(\d+)/);
      expect(maxAge).not.toBeNull();
      expect(Number(maxAge![1])).toBeGreaterThanOrEqual(31_536_000);
    });

    it("videos keep their week of `immutable`, also only when served", () => {
      const videoRule = hit.find((r) => matches(r, "/video/intro.mp4"));
      expect(videoRule).toBeDefined();
      expect(videoRule!.headers!["Cache-Control"]).toMatch(/max-age=604800\b/);
    });
  });

  describe("security headers", () => {
    // Before the filesystem check on purpose: a 404 and a proxied response
    // need them as much as a page does.
    const generalRule = main.find((r) => matches(r, "/courses") && r.headers !== undefined);

    it("exist and apply to app routes and missing assets alike", () => {
      expect(generalRule).toBeDefined();
      expect(generalRule!.continue).toBe(true);
      expect(matches(generalRule!, "/assets/gone-ABC.js")).toBe(true);
    });

    it("set a Content-Security-Policy that denies framing", () => {
      expect(generalRule!.headers!["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
    });
  });
});

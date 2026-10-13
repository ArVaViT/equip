/**
 * The sitemap generator's rules.
 *
 * Search Console, 2026-10-13: the sitemap listed `/login`, `/register`,
 * `/forgot-password` and `/verify`, and not one course. These pin the fix —
 * the static list, the committed fallback, the robots.txt agreement, and the
 * fallback when the API cannot be reached. No test here touches the network.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  STATIC_PAGES,
  buildDynamicSitemap,
  courseEntries,
  isAllowed,
  organizationEntries,
  parseRobots,
  readRobotsRules,
  renderSitemap,
  // @ts-expect-error — plain ESM build script, no type declarations by design.
} from "../build-sitemap.mjs";

const PUBLIC_DIR = join(import.meta.dirname, "..", "..", "public");
const COURSE_ID = "b8d24482-f630-49dc-990a-72ddb0717de0";

function locs(xml: string): string[] {
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
}

function fakeFetch(routes: Record<string, unknown>) {
  return async (url: string) => {
    const key = Object.keys(routes).find((k) => url.includes(k));
    if (!key) return { ok: false, status: 404, json: async () => ({}) };
    const body = routes[key];
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body };
  };
}

describe("static pages", () => {
  it("leaves out the forms that have nothing to find", () => {
    const paths = STATIC_PAGES.map((p: { path: string }) => p.path);
    for (const path of ["/login", "/register", "/forgot-password", "/verify", "/unsubscribe"]) {
      expect(paths).not.toContain(path);
    }
  });

  it("is what the committed public/sitemap.xml says", () => {
    const committed = readFileSync(join(PUBLIC_DIR, "sitemap.xml"), "utf8");
    expect(committed).toBe(renderSitemap(STATIC_PAGES, readRobotsRules()));
  });

  it("lists nothing robots.txt closes", () => {
    const rules = readRobotsRules();
    for (const p of STATIC_PAGES) expect(isAllowed(p.path, rules)).toBe(true);
  });
});

describe("robots.txt reading", () => {
  const rules = parseRobots(readFileSync(join(PUBLIC_DIR, "robots.txt"), "utf8"));

  it("lets the longer Allow win over a shorter Disallow", () => {
    expect(isAllowed("/teacher-terms", rules)).toBe(true);
    expect(isAllowed("/teacher", rules)).toBe(false);
    expect(isAllowed("/teacher/courses/x", rules)).toBe(false);
  });

  it("keeps course and organization pages open", () => {
    expect(isAllowed(`/courses/${COURSE_ID}`, rules)).toBe(true);
    expect(isAllowed("/o/some-school", rules)).toBe(true);
  });

  it("drops a disallowed URL from the rendered sitemap", () => {
    const xml = renderSitemap(
      [
        { path: "/", changefreq: "weekly", priority: "1.0" },
        { path: "/admin", changefreq: "weekly", priority: "1.0" },
      ],
      rules,
    );
    expect(locs(xml)).toEqual(["https://equipbible.com/"]);
  });
});

describe("course and organization entries", () => {
  it("takes published public courses with their last change", () => {
    const entries = courseEntries([
      { id: COURSE_ID, status: "published", access_mode: "public", updated_at: "2026-10-01T02:39:20.219015Z" },
      { id: "7924a1cf-8a84-4369-91ee-1f293f0f23df", status: "draft", access_mode: "public" },
      { id: "4f8d5432-4510-43d8-bc2b-00acc677d99e", status: "published", access_mode: "institute" },
      { id: "not-a-uuid", status: "published", access_mode: "public" },
      { id: COURSE_ID, status: "published", access_mode: "public" },
    ]);
    expect(entries).toEqual([
      { path: `/courses/${COURSE_ID}`, lastmod: "2026-10-01", changefreq: "weekly", priority: "0.8" },
    ]);
  });

  it("refuses a response that is not a list", () => {
    expect(() => courseEntries({ detail: "nope" })).toThrow();
  });

  it("takes only slugs that are safe in a path", () => {
    const entries = organizationEntries([{ slug: "grace-school" }, { slug: "../admin" }, { slug: "Bad Slug" }]);
    expect(entries.map((e: { path: string }) => e.path)).toEqual(["/o/grace-school"]);
  });
});

describe("buildDynamicSitemap", () => {
  const robotsRules = readRobotsRules();
  const silent = () => {};

  it("adds courses and organizations to the static pages", async () => {
    const result = await buildDynamicSitemap({
      apiOrigin: "https://api.example.test/",
      robotsRules,
      log: silent,
      fetchImpl: fakeFetch({
        "/api/v1/courses": [{ id: COURSE_ID, status: "published", access_mode: "public", updated_at: "2026-10-01T00:00:00Z" }],
        "/api/v1/organizations": [{ slug: "grace-school" }],
      }),
    });
    const urls = locs(result.xml);
    expect(urls).toContain(`https://equipbible.com/courses/${COURSE_ID}`);
    expect(urls).toContain("https://equipbible.com/o/grace-school");
    expect(urls).toHaveLength(STATIC_PAGES.length + 2);
  });

  it("gives up (keeping the static file) when courses cannot be read", async () => {
    const result = await buildDynamicSitemap({
      apiOrigin: "https://api.example.test",
      robotsRules,
      log: silent,
      fetchImpl: fakeFetch({ "/api/v1/courses": new Error("ENOTFOUND") }),
    });
    expect(result).toBeNull();
  });

  it("still lists courses when only the organization showcase fails", async () => {
    const result = await buildDynamicSitemap({
      apiOrigin: "https://api.example.test",
      robotsRules,
      log: silent,
      fetchImpl: fakeFetch({ "/api/v1/courses": [{ id: COURSE_ID, status: "published", access_mode: "public" }] }),
    });
    expect(locs(result.xml)).toContain(`https://equipbible.com/courses/${COURSE_ID}`);
  });
});

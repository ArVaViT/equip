/**
 * The per-page heads written after `vite build` (scripts/prerender-pages.mjs).
 *
 * Run against the real `index.html`: the generator edits tags in place and
 * throws when one is missing, so a change to the template that would make the
 * copies carry the home page's head fails here first.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DESCRIPTION_MAX,
  absoluteImage,
  coursePageData,
  renderCoursePage,
  truncate,
  withCanonical,
  // @ts-expect-error — plain ESM build script, no type declarations by design.
} from "../prerender-pages.mjs";

const TEMPLATE = readFileSync(join(import.meta.dirname, "..", "..", "index.html"), "utf8");
const ID = "b8d24482-f630-49dc-990a-72ddb0717de0";

const COURSE = {
  id: ID,
  title: "Teaching Course - I",
  description: "To study the biblical ministry of teaching. ".repeat(10) + "</script><b>x</b>",
  image_url: `/img/course-assets/${ID}/cover.png`,
  access_mode: "public",
  status: "published",
  organization_name: "UCOAT",
  updated_at: "2026-10-01T02:39:20.219015Z",
};

function count(html: string, re: RegExp): number {
  return (html.match(new RegExp(re.source, "g")) ?? []).length;
}

function jsonLdBlocks(html: string): Array<Record<string, unknown>> {
  return [...html.matchAll(/<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)].map((m) =>
    JSON.parse(m[1]!),
  );
}

describe("a course page's head", () => {
  const html = renderCoursePage(TEMPLATE, coursePageData(COURSE));

  it("names the course, once each", () => {
    expect(count(html, /<title>/)).toBe(1);
    expect(html).toContain("<title>Teaching Course - I — Equip</title>");
    expect(count(html, /<link rel="canonical" href=/)).toBe(1);
    expect(html).toContain(`<link rel="canonical" href="https://equipbible.com/courses/${ID}" />`);
    expect(html).toContain(`<meta property="og:url" content="https://equipbible.com/courses/${ID}" />`);
    expect(count(html, /<meta name="description"/)).toBe(1);
  });

  it("describes it in at most the snippet length, without markup", () => {
    const description = html.match(/<meta name="description" content="([^"]*)"/)![1]!;
    expect(description.length).toBeLessThanOrEqual(DESCRIPTION_MAX);
    expect(description).toMatch(/^To study the biblical ministry/);
    expect(description).not.toContain("&lt;");
  });

  it("uses the course cover for the share card, without the site card's size", () => {
    expect(html).toContain(`<meta property="og:image" content="https://equipbible.com/img/course-assets/${ID}/cover.png" />`);
    expect(html).not.toContain("og:image:width");
  });

  it("marks itself so locale-boot leaves the title alone", () => {
    expect(html).toContain(`data-prerendered="/courses/${ID}"`);
  });

  it("carries a schema.org Course built only from the API's facts", () => {
    const course = jsonLdBlocks(html).find((b) => b["@type"] === "Course")!;
    expect(course).toMatchObject({
      name: "Teaching Course - I",
      url: `https://equipbible.com/courses/${ID}`,
      inLanguage: "en",
      isAccessibleForFree: true,
      provider: { "@type": "Organization", name: "Equip" },
    });
    // A description holding `</script>` cannot close the block early.
    expect(count(html, /<\/script>/)).toBe(count(TEMPLATE, /<\/script>/) + 1);
  });

  it("does not claim free access for an invitation-only course", () => {
    const page = coursePageData({ ...COURSE, access_mode: "institute" });
    const course = jsonLdBlocks(renderCoursePage(TEMPLATE, page)).find((b) => b["@type"] === "Course")!;
    expect(course.isAccessibleForFree).toBeUndefined();
  });

  it("is not written for a course with no title in English", () => {
    expect(coursePageData({ ...COURSE, title: "" })).toBeNull();
  });
});

describe("helpers", () => {
  it("points a static page's canonical at itself", () => {
    const html = withCanonical(TEMPLATE, "/verify");
    expect(html).toContain('<link rel="canonical" href="https://equipbible.com/verify" />');
    expect(html).toContain('<meta property="og:url" content="https://equipbible.com/verify" />');
  });

  it("cuts at a word boundary", () => {
    const cut = truncate("word ".repeat(60));
    expect(cut.length).toBeLessThanOrEqual(DESCRIPTION_MAX);
    expect(cut.endsWith("word…")).toBe(true);
  });

  it("only makes same-site or https images absolute", () => {
    expect(absoluteImage("/img/a.png")).toBe("https://equipbible.com/img/a.png");
    expect(absoluteImage("//evil.example/a.png")).toBeNull();
    expect(absoluteImage("javascript:alert(1)")).toBeNull();
  });
});

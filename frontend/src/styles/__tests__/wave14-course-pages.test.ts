/**
 * Sentinel for ADR-0011 Wave 14 — Course detail/listing pages,
 * Chapter & Module views, DailyChallenge archive, student Dashboard
 * (+ public landing) migrated to v2.
 *
 * This is the heart of the student-facing surface: the catalog, the
 * course detail page (both enrolled and not-enrolled states), the
 * inside-a-course chapter + module reading views, the
 * DailyChallengeArchive history, and the logged-in dashboard root.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "..", "..");

function readNonComment(path: string): string {
  return readFileSync(path, "utf-8")
    .replace(/\/\/[^\n]*\n/g, "\n")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

function containsClass(code: string, className: string): boolean {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`).test(code);
}

const FILES = [
  resolve(SRC, "pages/Course/ChapterView.tsx"),
  resolve(SRC, "pages/Course/ModuleView.tsx"),
  resolve(SRC, "pages/Course/detail/CohortSelectModal.tsx"),
  resolve(SRC, "pages/Course/detail/EnrolledHeader.tsx"),
  resolve(SRC, "pages/Course/detail/ModuleList.tsx"),
  resolve(SRC, "pages/Course/detail/NotEnrolledView.tsx"),
  resolve(SRC, "pages/Course/detail/UpcomingEvents.tsx"),
  resolve(SRC, "pages/Courses/CoursesPage.tsx"),
  resolve(SRC, "pages/DailyChallengeArchive/DailyChallengeArchivePage.tsx"),
  resolve(SRC, "pages/Dashboard/DashboardPage.tsx"),
  resolve(SRC, "pages/Dashboard/PublicLanding.tsx"),
];

const V1_LOCKED_OUT = [
  "bg-background",
  "text-foreground",
  "text-muted-foreground",
  "border-border",
  "border-input",
  "bg-primary",
  "text-primary",
  "border-primary",
  "hover:bg-accent",
  "hover:text-accent-foreground",
  "ring-ring",
  "bg-muted-foreground",
];

describe("ADR-0011 Wave 14 — Course pages + Dashboard + DailyChallengeArchive", () => {
  for (const path of FILES) {
    const name = path.split(/[\\/]/).slice(-3).join("/");

    it(`${name} retired the v1 names`, () => {
      const code = readNonComment(path);
      for (const cls of V1_LOCKED_OUT) {
        expect(
          containsClass(code, cls),
          `${name} still references ${cls}`,
        ).toBe(false);
      }
    });
  }
});

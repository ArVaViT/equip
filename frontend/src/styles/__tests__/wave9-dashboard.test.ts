/**
 * Sentinel for ADR-0011 Wave 9 — dashboard & first-run surfaces
 * migrated to v2.
 *
 * Covers the next-most-visible surface after the layout chrome:
 * the dashboard cards a student sees every visit, the home page
 * Verse-of-the-Day card, and the entire first-run onboarding flow.
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
  resolve(SRC, "components/dashboard/DailyChallengeCard.tsx"),
  resolve(SRC, "components/dashboard/TodayCard.tsx"),
  resolve(SRC, "components/dashboard/WelcomeCard.tsx"),
  resolve(SRC, "components/home/VerseOfTheDayCard.tsx"),
  resolve(SRC, "components/firstRun/CoursePickerStep.tsx"),
  resolve(SRC, "components/firstRun/EnrollSplash.tsx"),
  resolve(SRC, "components/firstRun/FirstRunFlow.tsx"),
  resolve(SRC, "components/firstRun/PrivacyPolicyStep.tsx"),
  resolve(SRC, "components/firstRun/SetupStep.tsx"),
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

describe("ADR-0011 Wave 9 — dashboard & first-run surface migration", () => {
  for (const path of FILES) {
    const name = path.split(/[\\/]/).slice(-2).join("/");

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

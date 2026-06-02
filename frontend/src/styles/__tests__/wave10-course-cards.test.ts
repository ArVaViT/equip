/**
 * Sentinel for ADR-0011 Wave 10 — course cards, course modals,
 * admin atoms, remaining editor surfaces, and the InlineEdit
 * pattern.
 *
 * Brings the public-facing course-browsing surface, the
 * editor-toolbar / callout dropdown remnants, and the InlineEdit
 * primitive onto v2. After this wave the catalog + course detail
 * page are end-to-end on the v2 vocabulary.
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
  resolve(SRC, "components/course/CertificateCard.tsx"),
  resolve(SRC, "components/course/CompletionDialog.tsx"),
  resolve(SRC, "components/course/CourseCard.tsx"),
  resolve(SRC, "components/course/CourseReviews.tsx"),
  resolve(SRC, "components/admin/RoleSelector.tsx"),
  resolve(SRC, "components/admin/UserAvatar.tsx"),
  resolve(SRC, "components/editor/CalloutDropdown.tsx"),
  resolve(SRC, "components/editor/EditorToolbar.tsx"),
  resolve(SRC, "components/patterns/InlineEdit.tsx"),
  resolve(SRC, "components/patterns/InlineEditCover.tsx"),
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

describe("ADR-0011 Wave 10 — course cards + admin atoms + editor remnants migration", () => {
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

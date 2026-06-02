/**
 * Sentinel for ADR-0011 Wave 16 — UI primitive leftovers + lib
 * helpers migrated to v2.
 *
 * Closes out the last v1 references in the shadcn primitive layer
 * that earlier waves only partially migrated (variant blocks, disabled
 * states, sonner toast theme, date-picker chrome) plus the two lib/
 * helpers that hard-code class strings (chapterTypes, codeblock-copy).
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
  resolve(SRC, "components/ui/badge.tsx"),
  resolve(SRC, "components/ui/buttonVariants.ts"),
  resolve(SRC, "components/ui/date-picker.tsx"),
  resolve(SRC, "components/ui/date-range-picker.tsx"),
  resolve(SRC, "components/ui/datetime-picker.tsx"),
  resolve(SRC, "components/ui/dialog.tsx"),
  resolve(SRC, "components/ui/dropdown-menu.tsx"),
  resolve(SRC, "components/ui/PageSpinner.tsx"),
  resolve(SRC, "components/ui/radio-group.tsx"),
  resolve(SRC, "components/ui/select.tsx"),
  resolve(SRC, "components/ui/sheet.tsx"),
  resolve(SRC, "components/ui/sonner.tsx"),
  resolve(SRC, "components/ui/textareaVariants.ts"),
  resolve(SRC, "lib/chapterTypes.ts"),
  resolve(SRC, "lib/codeblock-copy.ts"),
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

describe("ADR-0011 Wave 16 — UI primitive leftovers + lib helpers", () => {
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

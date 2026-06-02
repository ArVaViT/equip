/**
 * Sentinel for ADR-0011 Wave 8 — layout & navigation surface
 * migrated to v2.
 *
 * Covers the high-traffic shell every page renders inside of:
 * AuthLayout / Footer / Header (+ subcomponents) / NotificationBell
 * (+ panel + items + meta) / ScrollToTop, plus AnnouncementBanner /
 * AnnouncementPager, ErrorBoundary, and the root App.tsx.
 *
 * If any of these regresses to a v1 token, the entire app's chrome
 * goes off-palette — the Wave 8 surface is the single most visible
 * area in the product.
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
  resolve(SRC, "App.tsx"),
  resolve(SRC, "components/ErrorBoundary.tsx"),
  resolve(SRC, "components/announcements/AnnouncementBanner.tsx"),
  resolve(SRC, "components/announcements/AnnouncementPager.tsx"),
  resolve(SRC, "components/layout/AuthLayout.tsx"),
  resolve(SRC, "components/layout/Footer.tsx"),
  resolve(SRC, "components/layout/Header.tsx"),
  resolve(SRC, "components/layout/NotificationBell.tsx"),
  resolve(SRC, "components/layout/ScrollToTop.tsx"),
  resolve(SRC, "components/layout/header/HeaderMobileMenuTrigger.tsx"),
  resolve(SRC, "components/layout/header/HeaderMobileSheet.tsx"),
  resolve(SRC, "components/layout/header/HeaderNavLink.tsx"),
  resolve(SRC, "components/layout/notifications/NotificationItem.tsx"),
  resolve(SRC, "components/layout/notifications/notificationMeta.ts"),
  resolve(SRC, "components/layout/notifications/NotificationPanel.tsx"),
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

describe("ADR-0011 Wave 8 — layout & navigation surface migration", () => {
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

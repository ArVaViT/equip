/**
 * Sentinel for ADR-0011 Wave 13 — Auth flow, Calendar, Certificates,
 * Profile, and NotFound pages migrated to v2.
 *
 * Covers the entire authentication entrypoint (login, register,
 * forgot/reset password, OAuth callback, register success / dup-email
 * views), the Calendar surface (page, grid, panels, constants), the
 * Certificates listing, the user Profile page, and the 404 fallback.
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
  resolve(SRC, "pages/Auth/AuthCallback.tsx"),
  resolve(SRC, "pages/Auth/ForgotPassword.tsx"),
  resolve(SRC, "pages/Auth/Login.tsx"),
  resolve(SRC, "pages/Auth/ResetPassword.tsx"),
  resolve(SRC, "pages/Auth/register/DuplicateEmailView.tsx"),
  resolve(SRC, "pages/Auth/register/RegisterForm.tsx"),
  resolve(SRC, "pages/Auth/register/SuccessView.tsx"),
  resolve(SRC, "pages/Calendar/CalendarPage.tsx"),
  resolve(SRC, "pages/Calendar/MonthGrid.tsx"),
  resolve(SRC, "pages/Calendar/SelectedDayPanel.tsx"),
  resolve(SRC, "pages/Calendar/UpcomingEventsPanel.tsx"),
  resolve(SRC, "pages/Calendar/constants.ts"),
  resolve(SRC, "pages/Certificates/CertificatesPage.tsx"),
  resolve(SRC, "pages/NotFound.tsx"),
  resolve(SRC, "pages/Profile/ProfilePage.tsx"),
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

describe("ADR-0011 Wave 13 — Auth + Calendar + Certs + Profile + 404", () => {
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

/**
 * Sentinel for ADR-0011 Wave 12 — Admin pages migrated to v2.
 *
 * Covers the entire Admin surface: AdminDashboard root + the
 * cohorts pages (detail, status picker, attach-course, add-student,
 * tab), the Daily Challenge review pages, and the dashboard tab
 * subcomponents (audit-log, audit-details, overview stats, pending
 * certs card, users card, filter field).
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
  resolve(SRC, "pages/Admin/AdminDashboard.tsx"),
  resolve(SRC, "pages/Admin/VirtualAdminUsers.tsx"),
  resolve(SRC, "pages/Admin/cohorts/AddStudentDialog.tsx"),
  resolve(SRC, "pages/Admin/cohorts/AttachCourseDialog.tsx"),
  resolve(SRC, "pages/Admin/cohorts/CohortDetailPage.tsx"),
  resolve(SRC, "pages/Admin/cohorts/CohortStatusPicker.tsx"),
  resolve(SRC, "pages/Admin/cohorts/CohortsTab.tsx"),
  resolve(SRC, "pages/Admin/dailyChallenge/DailyChallengeReviewDetailPage.tsx"),
  resolve(SRC, "pages/Admin/dailyChallenge/DailyChallengeReviewPage.tsx"),
  resolve(SRC, "pages/Admin/dashboard/AdminTabs.tsx"),
  resolve(SRC, "pages/Admin/dashboard/AuditDetailsCell.tsx"),
  resolve(SRC, "pages/Admin/dashboard/AuditLogTab.tsx"),
  resolve(SRC, "pages/Admin/dashboard/AuditSummaryRow.tsx"),
  resolve(SRC, "pages/Admin/dashboard/FilterField.tsx"),
  resolve(SRC, "pages/Admin/dashboard/OverviewStats.tsx"),
  resolve(SRC, "pages/Admin/dashboard/PendingCertsCard.tsx"),
  resolve(SRC, "pages/Admin/dashboard/UsersCard.tsx"),
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

describe("ADR-0011 Wave 12 — Admin pages migration", () => {
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

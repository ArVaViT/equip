/**
 * Sentinel for ADR-0011 Wave 15 — entire Teacher surface migrated
 * to v2.
 *
 * The largest single-wave migration: 27 files covering Teacher
 * dashboard + course-editor + module-editor + chapter-editor +
 * gradebook + student-progress + analytics + the inside-Teacher
 * modals (access mode, materials, events, readiness card).
 *
 * Once this wave merges, the v2 vocabulary owns every page the
 * teacher persona touches.
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
  // Teacher pages (root)
  "pages/Teacher/ChapterEditor.tsx",
  "pages/Teacher/ModuleEditor.tsx",
  "pages/Teacher/StudentProgress.tsx",
  "pages/Teacher/TeacherAnalytics.tsx",
  "pages/Teacher/TeacherDashboard.tsx",
  "pages/Teacher/TeacherGradebook.tsx",
  // Teacher dashboard sub-cards
  "pages/Teacher/dashboard/CourseCard.tsx",
  "pages/Teacher/dashboard/CreateCourseForm.tsx",
  "pages/Teacher/dashboard/EmptyCoursesCard.tsx",
  "pages/Teacher/dashboard/PendingCertsCard.tsx",
  "pages/Teacher/dashboard/TrashSection.tsx",
  // Teacher editor modals + cards
  "pages/Teacher/editor/AccessModeModal.tsx",
  "pages/Teacher/editor/CourseReadinessCard.tsx",
  "pages/Teacher/editor/EventsModal.tsx",
  "pages/Teacher/editor/MaterialsModal.tsx",
  "pages/Teacher/editor/ModulesList.tsx",
  // Gradebook
  "pages/Teacher/gradebook/GradebookTabs.tsx",
  "pages/Teacher/gradebook/GradeTableTab.tsx",
  "pages/Teacher/gradebook/GradingConfigCard.tsx",
  "pages/Teacher/gradebook/helpers.tsx",
  "pages/Teacher/gradebook/SummaryTab.tsx",
  // Module editor sub
  "pages/Teacher/moduleEditor/AddChapterBar.tsx",
  "pages/Teacher/moduleEditor/ChapterRow.tsx",
  // Student progress sub
  "pages/Teacher/progress/ChapterBreakdownRow.tsx",
  "pages/Teacher/progress/ProgressBar.tsx",
  "pages/Teacher/progress/StudentRow.tsx",
  "pages/Teacher/progress/StudentTable.tsx",
].map((rel) => resolve(SRC, rel));

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

describe("ADR-0011 Wave 15 — Teacher surface migration", () => {
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

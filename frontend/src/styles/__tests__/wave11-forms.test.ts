/**
 * Sentinel for ADR-0011 Wave 11 — assignment & quiz forms migrated
 * to v2.
 *
 * Covers two of the most frequented teacher + student surfaces:
 * assignment editor / panel / item / submission grader, and the
 * full quiz authoring + taking + reviewing surface (editor, mode
 * toggle, question card, quiz taker components, results view,
 * previous attempts, essay answer, header, submissions review).
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
  resolve(SRC, "components/assignment/AssignmentEditor.tsx"),
  resolve(SRC, "components/assignment/AssignmentPanel.tsx"),
  resolve(SRC, "components/assignment/editor/AssignmentItem.tsx"),
  resolve(SRC, "components/assignment/editor/SubmissionGrader.tsx"),
  resolve(SRC, "components/quiz/editor/ModeToggle.tsx"),
  resolve(SRC, "components/quiz/editor/QuestionCard.tsx"),
  resolve(SRC, "components/quiz/QuizEditor.tsx"),
  resolve(SRC, "components/quiz/QuizSubmissionsReview.tsx"),
  resolve(SRC, "components/quiz/QuizTaker.tsx"),
  resolve(SRC, "components/quiz/taker/EssayAnswer.tsx"),
  resolve(SRC, "components/quiz/taker/PreviousAttempts.tsx"),
  resolve(SRC, "components/quiz/taker/QuestionPrompt.tsx"),
  resolve(SRC, "components/quiz/taker/QuizHeader.tsx"),
  resolve(SRC, "components/quiz/taker/ResultsView.tsx"),
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

describe("ADR-0011 Wave 11 — assignment & quiz forms migration", () => {
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

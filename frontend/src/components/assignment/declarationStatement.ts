/**
 * The text the student actually saw, assembled for storage.
 *
 * Sent back with the submission so the record holds what was on their screen
 * rather than a key into a catalogue somebody edits next month — the same
 * principle the ведомость, the certificate and the legal agreements run on.
 *
 * Three lines, in the order they stand on the screen: the course's rule, the
 * answer the student chose («Без ИИ» / «С ИИ»), and the sentence above the
 * submit button that makes pressing it the confirmation.
 */
import type { AiPolicy } from "@/types"

export type AiUse = "none" | "assisted"

export interface DeclarationState {
  /** `null` until the student has answered; the submit button waits for it. */
  aiUse: AiUse | null
  /** Their own words on what they used it for, where the course asks. */
  note: string
}

export const BLANK_DECLARATION: DeclarationState = { aiUse: null, note: "" }

export function declarationPolicyKey(policy: AiPolicy): "ai_forbidden" | "ai_with_disclosure" {
  return policy === "ai_forbidden" ? "ai_forbidden" : "ai_with_disclosure"
}

export function declarationStatement(policy: AiPolicy, aiUse: AiUse, t: (k: string) => string): string {
  return [
    t(`declaration.${declarationPolicyKey(policy)}.rule`),
    t(aiUse === "assisted" ? "declaration.withAi" : "declaration.withoutAi"),
    t("declaration.bySubmitting"),
  ].join("\n")
}

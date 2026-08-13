/**
 * The text the student actually saw, assembled for storage.
 *
 * Sent back with the submission so the record holds what was on their screen
 * rather than a key into a catalogue somebody edits next month — the same
 * principle the ведомость, the certificate and the legal agreements run on.
 */
import type { AiPolicy } from "@/types"

export function declarationStatement(policy: AiPolicy, t: (k: string) => string): string {
  const key = policy === "ai_forbidden" ? "ai_forbidden" : "ai_with_disclosure"
  return [
    t(`declaration.${key}.policy`),
    t(`declaration.${key}.example`),
    t(`declaration.${key}.consequence`),
    t("declaration.confirm"),
  ].join("\n")
}

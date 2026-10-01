import type { Certificate } from "@/types"

/** The public page that confirms the certificate — what a share should point at. */
export function verifyUrl(cert: Pick<Certificate, "certificate_number">, origin: string): string {
  return `${origin}/verify/${encodeURIComponent(cert.certificate_number ?? "")}`
}

/**
 * LinkedIn's own "add a certification to your profile" form, filled in:
 * the course, the school (or Equip when it has no name), the month of
 * issue, the number and the page that verifies it. The student reviews
 * and saves it on LinkedIn; nothing is posted for them.
 */
export function linkedInAddUrl(
  cert: Pick<Certificate, "certificate_number" | "issued_at" | "course_title" | "archived_course_title" | "school_name">,
  origin: string,
  /** The zone the document prints its date in, so both say the same month. */
  timeZone: string,
): string {
  const params = new URLSearchParams({
    startTask: "CERTIFICATION_NAME",
    name: cert.course_title ?? cert.archived_course_title ?? "",
    organizationName: cert.school_name || "Equip",
    certUrl: verifyUrl(cert, origin),
    certId: cert.certificate_number ?? "",
  })
  if (cert.issued_at) {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone, year: "numeric", month: "numeric" }).formatToParts(
      new Date(cert.issued_at),
    )
    params.set("issueYear", parts.find((p) => p.type === "year")!.value)
    params.set("issueMonth", String(Number(parts.find((p) => p.type === "month")!.value)))
  }
  return `https://www.linkedin.com/profile/add?${params.toString()}`
}

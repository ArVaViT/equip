import { zonedDayKey } from "@/i18n/timeZone"
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
  cert: Pick<
    Certificate,
    "certificate_number" | "issued_at" | "issued_on" | "course_title" | "archived_course_title" | "school_name"
  >,
  origin: string,
  /** Only for a certificate without `issued_on` (an older server): the zone
   *  its day is read in. The school's day, when there is one, wins. */
  timeZone: string,
): string {
  const params = new URLSearchParams({
    startTask: "CERTIFICATION_NAME",
    name: cert.course_title ?? cert.archived_course_title ?? "",
    organizationName: cert.school_name || "Equip",
    certUrl: verifyUrl(cert, origin),
    certId: cert.certificate_number ?? "",
  })
  // The month the document prints: the school's day, as the server fixed it.
  const day = cert.issued_on ?? (cert.issued_at ? zonedDayKey(new Date(cert.issued_at), timeZone) : null)
  if (day) {
    params.set("issueYear", day.slice(0, 4))
    params.set("issueMonth", String(Number(day.slice(5, 7))))
  }
  return `https://www.linkedin.com/profile/add?${params.toString()}`
}

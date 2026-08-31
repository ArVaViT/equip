import type { Certificate } from "@/types"

/**
 * What counts as a certificate somebody actually has.
 *
 * A row in `certificates` is a *request*: it can be pending, approved by a
 * teacher but not yet by an admin, rejected, or awarded. Counting rows and
 * calling the total "earned" produced the same untruth in two places
 * independently — the certificates page said "14 certificates earned" above
 * fourteen cards each marked "Rejected", and the profile said "14
 * Certificates Earned" beside "0 Courses Completed".
 *
 * Fixing the first one did not fix the second, because each screen had its
 * own idea of what earned means. There is one here now, and a test that
 * fails if a screen goes back to counting rows.
 */
export function isAwardedCertificate(certificate: Pick<Certificate, "status">): boolean {
  return certificate.status === "approved"
}

export function countAwarded(certificates: ReadonlyArray<Pick<Certificate, "status">>): number {
  return certificates.filter(isAwardedCertificate).length
}

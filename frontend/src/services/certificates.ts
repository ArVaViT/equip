import api from "./api"
import { isAxiosError } from "axios"
import type { Certificate } from "@/types"

/** What the public verification endpoint answers. No PII when invalid. */
export interface CertificateVerification {
  valid: boolean
  certificate_number: string
  user_name: string | null
  course_title: string | null
  issued_at: string | null
}

export const certificatesService = {
  /**
   * Look a certificate up by the number printed on it. No authentication:
   * the whole point is that somebody who was handed the certificate — an
   * employer, a pastor, another school — can check it without an account.
   */
  async verifyCertificate(certificateNumber: string): Promise<CertificateVerification> {
    const response = await api.get<CertificateVerification>(
      `/certificates/verify/${encodeURIComponent(certificateNumber)}`,
    )
    return response.data
  },

  async getCourseCertificate(courseId: string): Promise<Certificate | null> {
    try {
      const response = await api.get<Certificate>(`/certificates/course/${courseId}`)
      return response.data
    } catch (err: unknown) {
      if (isAxiosError(err) && err.response?.status === 404) return null
      throw err
    }
  },

  async requestCertificate(courseId: string): Promise<Certificate> {
    const response = await api.post<Certificate>(`/certificates/course/${courseId}`)
    return response.data
  },

  async getMyCertificates(): Promise<Certificate[]> {
    const response = await api.get<Certificate[]>("/certificates/my")
    return response.data
  },

  async getPendingCertificates(): Promise<Certificate[]> {
    const response = await api.get<Certificate[]>("/certificates/pending")
    return response.data
  },

  async teacherApproveCert(certId: string): Promise<void> {
    await api.put(`/certificates/${certId}/teacher-approve`)
  },

  async adminApproveCert(certId: string): Promise<void> {
    await api.put(`/certificates/${certId}/admin-approve`)
  },

  async rejectCert(certId: string): Promise<void> {
    await api.put(`/certificates/${certId}/reject`)
  },

  async getAdminPendingCerts(): Promise<Certificate[]> {
    const response = await api.get<Certificate[]>("/certificates/admin/pending")
    return response.data
  },
}

import api from "./api"

export interface LegalDocument {
  slug: string
  version: string
  locale: string
  body: string
  sha256: string
}

export interface LegalDocumentSummary {
  slug: string
  version: string
  /** The date this version took effect (ISO ``YYYY-MM-DD``). */
  effective: string
  /** Roles that must accept it. Empty for a page nobody signs. */
  required_for: string[]
  /**
   * Whether arriving at this version asks for a fresh acceptance. A version
   * published with this ``false`` reaches people as a notice — which is the
   * mechanism that lets a typo be fixed without a hundred people clicking a
   * consent screen they have stopped reading.
   */
  requires_consent: boolean
}

export interface LegalAcceptance {
  slug: string
  version: string
  locale: string
  accepted_at: string
}

export interface LegalStatus {
  accepted: LegalAcceptance[]
  /**
   * What this person still has to accept. The server answers it, not us —
   * and it answers for the role on their profile row, which is how a
   * promotion to teacher reaches a tab that has not re-read its own profile.
   */
  outstanding: LegalDocumentSummary[]
  /** Documents that changed since they signed, without changing the deal. */
  notices: LegalDocumentSummary[]
}

/**
 * The documents, and the record of accepting them.
 *
 * `accept` deliberately sends no body text. A client that supplies the text it
 * says it displayed can supply any text; the server hashes its own copy.
 */
export const legalService = {
  /** What must be accepted, and at which version. Public. */
  async documents(): Promise<LegalDocumentSummary[]> {
    const response = await api.get<LegalDocumentSummary[]>("/legal/documents")
    return response.data
  },

  async document(slug: string, locale: string): Promise<LegalDocument> {
    const response = await api.get<LegalDocument>(`/legal/documents/${slug}`, { params: { locale } })
    return response.data
  },

  async status(): Promise<LegalStatus> {
    const response = await api.get<LegalStatus>("/legal/acceptances/me")
    return response.data
  },

  async accept(slug: string, version: string, locale: string): Promise<LegalAcceptance> {
    const response = await api.post<LegalAcceptance>("/legal/acceptances", { slug, version, locale })
    return response.data
  },
}

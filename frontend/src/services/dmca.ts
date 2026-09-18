import api from "./api"

/** Mirrors ``chk_dmca_complaints_status`` and the Python ``DmcaComplaintStatus``. */
export type DmcaStatus = "received" | "upheld" | "rejected" | "withdrawn"

export const DMCA_STATUSES = {
  RECEIVED: "received",
  UPHELD: "upheld",
  REJECTED: "rejected",
  WITHDRAWN: "withdrawn",
} as const satisfies Record<string, DmcaStatus>

/** The three a person may choose. `received` is where a row starts and is
 *  not somewhere it can be put back: un-deciding a complaint would erase a
 *  strike an account closure may already rest on. */
export type DmcaDecision = Exclude<DmcaStatus, "received">

export interface DmcaComplaint {
  id: string
  received_at: string
  complainant_name: string
  complainant_email: string
  complainant_organization: string | null
  work_described: string
  material_location: string
  uploaded_by: string | null
  uploader_name: string | null
  uploader_notified_at: string | null
  status: DmcaStatus
  resolved_at: string | null
  resolved_by: string | null
  resolution_note: string | null
  /** Where this one sat in the uploader's sequence when it was upheld. */
  strike_number: number | null
  /** Where that person stands today — the number somebody deciding the next
   *  complaint actually needs. */
  uploader_upheld_count: number
  uploader_account_closed: boolean
}

/**
 * The complaints ledger.
 *
 * Admin-only on both ends: the rows name a complainant and a member of the
 * school, and § 512 asks for a record rather than for a public register.
 */
export const dmcaService = {
  async list(params?: { status?: DmcaStatus }): Promise<DmcaComplaint[]> {
    const { data } = await api.get<DmcaComplaint[]>("/admin/dmca/complaints", {
      params,
    })
    return data
  },

  /** Write down a notice that arrived by email. */
  async record(body: {
    complainant_name: string
    complainant_email: string
    complainant_organization?: string | null
    work_described: string
    material_location: string
    uploaded_by?: string | null
  }): Promise<DmcaComplaint> {
    const { data } = await api.post<DmcaComplaint>("/admin/dmca/complaints", body)
    return data
  },

  /**
   * Record what was decided. One-way: the server refuses a second decision on
   * the same complaint, because a strike may already have closed an account
   * and renumbering the history would leave the ledger unable to explain it.
   */
  async decide(
    id: string,
    body: {
      status: DmcaDecision
      resolution_note?: string | null
      uploader_notified?: boolean
    },
  ): Promise<DmcaComplaint> {
    const { data } = await api.patch<DmcaComplaint>(
      `/admin/dmca/complaints/${encodeURIComponent(id)}`,
      body,
    )
    return data
  },
}

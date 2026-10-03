import api from "./api"
import type { MailKind } from "@/types"

/** What an unsubscribe link would turn off, and whether it already is. */
export interface UnsubscribeState {
  kind: MailKind
  off: boolean
}

/**
 * The link at the foot of a course mail. No sign-in: the token in the link
 * is the authority, and it can only turn one kind of mail off. Reading is a
 * separate call from acting so that a mail scanner opening the link turns
 * nothing off — the person presses the button.
 */
export const emailService = {
  async readUnsubscribe(token: string): Promise<UnsubscribeState> {
    const response = await api.get<UnsubscribeState>("/email/unsubscribe", { params: { token } })
    return response.data
  },

  async unsubscribe(token: string): Promise<UnsubscribeState> {
    const response = await api.post<UnsubscribeState>("/email/unsubscribe", null, { params: { token } })
    return response.data
  },
}

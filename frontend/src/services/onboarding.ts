import api from "./api"
import type { User } from "@/types"

/**
 * The one thing the first-run flow tells the server: that it has been
 * finished.
 *
 * Idempotent on the server — the timestamp is written once and never moved —
 * so a browser that still holds the old ``localStorage`` flag can report it
 * on every visit until the profile carries the mark. Returns the refreshed
 * profile; hand it to ``applyUser`` so nothing waits for the next reload.
 */
export const onboardingService = {
  async complete(): Promise<User> {
    const { data } = await api.post<User>("/users/me/onboarding/complete")
    return data
  },
}

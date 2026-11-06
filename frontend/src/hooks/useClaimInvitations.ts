import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/context/useAuth"
import { getAccountDeleted } from "@/lib/accountDeleted"
import { toast } from "@/lib/toast"
import { invitationsService } from "@/services/invitations"

/**
 * Accept, once a session, the invitations waiting for the signed-in address.
 *
 * The link in the email used to be the only way in. A person who came to the
 * site on their own — signed up, signed in with Google, or already had an
 * account — stayed a student in no school while the invitation expired
 * unseen. The server now accepts it for a proven address
 * (`POST /invitations/claim`); this asks it to, and when something was
 * accepted, reloads the profile so the new role shows without a reload and
 * says where the person now belongs.
 *
 * `enabled` is false on the auth pages: the invite page accepts its own
 * link there, and a claim racing it would turn that into «already used».
 */
export function useClaimInvitations(enabled: boolean): void {
  const { user, refreshUser } = useAuth()
  const { t } = useTranslation()
  const asked = useRef<string | null>(null)
  const userId = user?.id ?? null
  const closed = Boolean(user?.deleted_at || user?.deactivated_at)

  useEffect(() => {
    if (!enabled || !userId || closed || getAccountDeleted()) return
    if (asked.current === userId) return
    asked.current = userId
    invitationsService
      .claimInvitations()
      .then((claimed) => {
        if (claimed.length === 0) return
        void refreshUser()
        for (const invitation of claimed) {
          if (!invitation.organization_name) continue
          toast({
            variant: "success",
            title: t(invitation.role === "teacher" ? "invite.claimed.teach" : "invite.claimed.study", {
              organization: invitation.organization_name,
            }),
          })
        }
      })
      // Best effort: the next session asks again.
      .catch(() => {
        asked.current = null
      })
  }, [enabled, userId, closed, refreshUser, t])
}

import { useContext } from "react"

import { AuthContext } from "@/context/auth-context"
import { useAsyncData } from "@/hooks/useAsyncData"
import { notesService } from "@/services/notes"

/**
 * The lessons the reader has written a note on, so a list of lessons can
 * mark them. Empty until known, for a visitor, or when the request fails.
 */
export function useNotedChapters(): Set<string> {
  // Read without requiring a provider: an outline rendered on its own (its
  // tests, a preview) has no reader and nothing to mark.
  const user = useContext(AuthContext)?.user
  const { data } = useAsyncData(
    async () => (user ? new Set(await notesService.notedChapters().catch(() => [])) : new Set<string>()),
    [user?.id],
  )
  return data ?? new Set<string>()
}

import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { notesService } from "@/services/notes"

/**
 * The lessons the reader has written a note on, so a list of lessons can
 * mark them. Empty until known, for a visitor, or when the request fails.
 */
export function useNotedChapters(): Set<string> {
  const { user } = useAuth()
  const { data } = useAsyncData(
    async () => (user ? new Set(await notesService.notedChapters().catch(() => [])) : new Set<string>()),
    [user?.id],
  )
  return data ?? new Set<string>()
}

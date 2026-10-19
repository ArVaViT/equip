import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { useAsyncData } from "@/hooks/useAsyncData"
import { organizationsService, type MyOrganizationCourses } from "@/services/organizations"
import type { Course } from "@/types"

export type ClosedCoursesBlock = MyOrganizationCourses & { closed: Course[] }

/**
 * The reader's organizations that have a closed course to show — one block
 * each. Nobody signed in, nothing. A failed call is not nothing: the error
 * comes back with a `refetch`, since this is the only way to a member's
 * closed courses. Lifted out of the component so the page knows whether the
 * sections (and the «catalogue» heading that follows them) are on it: the
 * cards below take their heading level from that.
 */
export function useMyOrganizationsBlocks(userId: string | undefined): {
  blocks: ClosedCoursesBlock[]
  error: Error | null
  refetch: () => void
} {
  const { i18n } = useTranslation()
  const { data, error, refetch } = useAsyncData(
    () => (userId ? organizationsService.mine() : Promise.resolve([])),
    [userId, i18n.language],
  )
  const blocks = useMemo(
    () =>
      (data ?? [])
        .map((block) => ({ ...block, closed: block.courses.filter((c) => c.access_mode === "institute") }))
        .filter((block) => block.closed.length > 0),
    [data],
  )
  return { blocks, error, refetch }
}

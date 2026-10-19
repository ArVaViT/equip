import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Lock } from "lucide-react"

import CourseCard from "@/components/course/CourseCard"
import { Button } from "@/components/ui/button"
import { ErrorState, Eyebrow } from "@/components/patterns"

import type { ClosedCoursesBlock } from "./useMyOrganizationsBlocks"

/**
 * The closed courses of every organization the reader belongs to — the
 * reason to belong to one. The catalogue below lists only public courses;
 * without this, a member's closed courses were reachable by a link
 * somebody sent them and from nowhere else. One block per organization,
 * each to its page; organizations never mix.
 */
export function MyOrganizationsCourses({
  blocks,
  error,
  refetch,
  progress,
}: {
  blocks: ClosedCoursesBlock[]
  error: Error | null
  refetch: () => void
  progress: Map<string, number>
}) {
  const { t } = useTranslation()
  if (error) {
    // Not nothing: this is the only way to a member's closed courses, and
    // a catalogue that silently shows the public ones reads as «you have
    // no institute».
    return (
      <ErrorState
        className="mb-8 py-6"
        title={t("myOrganizations.loadFailed")}
        action={
          <Button size="sm" variant="outline" onClick={refetch}>
            {t("common.tryAgain")}
          </Button>
        }
      />
    )
  }
  if (blocks.length === 0) return null
  return (
    <div className="mb-8 space-y-10">
      {blocks.map((block) => (
        <section key={block.organization_id} aria-labelledby={`my-org-${block.organization_id}`}>
          <Eyebrow className="flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("myOrganizations.eyebrow", { role: t(`myOrganizations.roles.${block.role}`) })}
          </Eyebrow>
          <h2 id={`my-org-${block.organization_id}`} className="mt-1 font-serif text-2xl font-semibold tracking-tight">
            <Link to={`/o/${block.organization_slug}`} className="underline-offset-4 hover:underline">
              {block.organization_name}
            </Link>
          </h2>
          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-7 lg:grid-cols-3">
            {block.closed.map((course) => (
              <CourseCard key={course.id} course={course} progress={progress.get(course.id)} viewerIsMember />
            ))}
          </div>
        </section>
      ))}
      {/* The public catalogue follows; with blocks above it, it needs its own name. */}
      <h2 className="border-t border-edge pt-10 font-serif text-2xl font-semibold tracking-tight">
        {t("myOrganizations.catalog")}
      </h2>
    </div>
  )
}

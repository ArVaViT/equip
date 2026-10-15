import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Lock } from "lucide-react"

import CourseCard from "@/components/course/CourseCard"
import { Eyebrow } from "@/components/patterns"
import { useAsyncData } from "@/hooks/useAsyncData"
import { organizationsService } from "@/services/organizations"

/**
 * The closed courses of every organization the reader belongs to — the
 * reason to belong to one. The catalogue below lists only public courses;
 * without this, a member's closed courses were reachable by a link
 * somebody sent them and from nowhere else. One block per organization,
 * each to its page; organizations never mix.
 */
export function MyOrganizationsCourses({ userId, progress }: { userId: string; progress: Map<string, number> }) {
  const { t, i18n } = useTranslation()
  const { data } = useAsyncData(() => organizationsService.mine().catch(() => []), [userId, i18n.language])
  const blocks = (data ?? [])
    .map((block) => ({ ...block, closed: block.courses.filter((c) => c.access_mode === "institute") }))
    .filter((block) => block.closed.length > 0)
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

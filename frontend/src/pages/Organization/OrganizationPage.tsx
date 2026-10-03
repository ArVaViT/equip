import { useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight, BadgeCheck, BookOpen, ExternalLink, GraduationCap, Library, Lock, LogIn, Pencil, ScrollText, UserRound, Users } from "lucide-react"

import CourseCard from "@/components/course/CourseCard"
import { CourseCoverFallback } from "@/components/course/CourseCoverFallback"
import { EmptyState, ErrorState, Modal, PageHeader } from "@/components/patterns"
import { Section } from "@/components/layout/Section"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useNamedPageTitle } from "@/hooks/usePageTitle"
import { activeIntlTag } from "@/i18n/config"
import { toProxyImage } from "@/lib/images"
import { getErrorCode } from "@/lib/errorCode"
import { organizationInitials } from "@/lib/organizationInitials"
import { cn } from "@/lib/utils"
import { organizationsService, type LockedCourse, type OrganizationPage as Page } from "@/services/organizations"
import { OrganizationProfileForm } from "./OrganizationProfileForm"

/**
 * An organization's own page, `/o/:slug`: who it is, who runs it, what it
 * teaches. Where a certificate points, and what an organization is shown —
 * "these are teaching here" — when it is asked to join.
 */
export default function OrganizationPage() {
  const { slug = "" } = useParams<{ slug: string }>()
  const { t, i18n } = useTranslation()
  const [version, setVersion] = useState(0)
  const [editing, setEditing] = useState(false)
  const { data, loading, error } = useAsyncData(() => organizationsService.getPage(slug), [slug, version, i18n.language])
  useNamedPageTitle(data?.public_name)

  if (loading && !data) return <PageSpinner />
  if (error || !data) {
    const notFound = getErrorCode(error) === "resource.not_found"
    return (
      <Section>
        <ErrorState
          title={notFound ? t("organization.notFound") : t("organization.loadError")}
          action={
            <Link to="/courses">
              <Button variant="outline" size="sm">{t("organization.toCatalog")}</Button>
            </Link>
          }
        />
      </Section>
    )
  }

  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  // The place alone, above the name. «Организация · Индианаполис, США» said
  // "organization" to a reader who had just read the organization's name.
  const place = [data.city, data.country ? countryName(data.country, locale) : null].filter(Boolean).join(", ")
  // With the day: «с 3 октября 2026 г.» — month and year alone come out in
  // the nominative («с октябрь»), which no reader would write.
  const since = new Date(data.since).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })

  return (
    <Section>
      <PageHeader
        cover={<OrganizationLogo page={data} />}
        eyebrow={place || undefined}
        title={data.public_name}
        meta={
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            {data.verified && (
              // What "verified" stands for, on hover and to a screen reader:
              // the badge is the platform's claim, and a claim should say
              // what it covers.
              <span className="inline-flex items-center gap-1.5 font-medium text-success-ink" title={t("organization.verifiedHint")}>
                <BadgeCheck className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("organization.verified")}
                <span className="sr-only">. {t("organization.verifiedHint")}</span>
              </span>
            )}
            {data.website_url && (
              <a
                href={data.website_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-ink-muted underline-offset-4 hover:text-ink hover:underline"
              >
                <ExternalLink className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                {websiteLabel(data.website_url)}
              </a>
            )}
          </div>
        }
        actions={
          data.viewer_can_edit && data.id && !editing ? (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("organization.edit")}
            </Button>
          ) : null
        }
      />

      {editing && data.id ? (
        <OrganizationProfileForm
          organizationId={data.id}
          page={data}
          onDone={(changed) => {
            setEditing(false)
            if (changed) setVersion((v) => v + 1)
          }}
        />
      ) : (
        data.description && (
          <p className="mt-6 max-w-prose whitespace-pre-line text-base text-ink text-wrap-safe">{data.description}</p>
        )
      )}

      {data.directors.length > 0 && (
        <section aria-labelledby="org-directors" className="mt-8">
          <h2 id="org-directors" className="sr-only">
            {t("organization.director", { count: data.directors.length })}
          </h2>
          <ul className="flex flex-wrap gap-4">
            {data.directors.map((d) => (
              <li key={d.id} className="flex items-center gap-3">
                <PersonFace person={d} />
                <div>
                  <p className="text-sm font-medium">{d.full_name}</p>
                  <p className="text-xs text-ink-muted">{t("organization.director", { count: 1 })}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Stats page={data} />

      {!data.active ? (
        <div className="mt-10 rounded-card border border-edge bg-muted/30 p-6 text-sm text-ink-muted">
          {t("organization.inactive")}
        </div>
      ) : (
        <section aria-labelledby="org-courses" className="mt-12">
          <h2 id="org-courses" className="mb-5 font-serif text-2xl font-semibold tracking-tight">
            {t("organization.courses")}
          </h2>
          {data.courses.length === 0 && data.locked_courses.length === 0 ? (
            // To its director the empty shelf is a next step, not a verdict:
            // where courses come from, and the door to make one.
            <EmptyState
              icon={<BookOpen strokeWidth={1.75} aria-hidden />}
              title={t("organization.noCourses")}
              description={data.viewer_can_edit ? t("organization.noCoursesYet") : undefined}
              action={
                data.viewer_can_edit ? (
                  <Button asChild variant="outline" size="sm">
                    <Link to="/teacher">{t("organization.createCourse")}</Link>
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-7 lg:grid-cols-3">
              {data.courses.map((course) => (
                <CourseCard key={course.id} course={course} />
              ))}
              {data.locked_courses.map((course) => (
                <LockedCourseCard key={course.id} course={course} page={data} />
              ))}
            </div>
          )}
        </section>
      )}

      <footer className="mt-14 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-edge pt-5 text-sm text-ink-muted">
        <span>{t("organization.since", { date: since })}</span>
        <Link to="/verify" className="inline-flex items-center gap-1.5 underline-offset-4 hover:text-ink hover:underline">
          <ScrollText className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("organization.verifyCertificate")}
        </Link>
      </footer>
    </Section>
  )
}

function OrganizationLogo({ page }: { page: Page }) {
  const src = toProxyImage(page.logo_url)
  if (src) {
    return <img src={src} alt="" className="h-20 w-20 shrink-0 rounded-card border border-edge bg-surface object-contain" />
  }
  // No logo yet: the name's initials, quiet, in the place a logo goes.
  return (
    <div
      aria-hidden
      className="flex h-20 w-20 shrink-0 items-center justify-center rounded-card border border-edge bg-muted/40 font-serif text-3xl font-semibold text-ink-muted"
    >
      {organizationInitials(page.public_name)}
    </div>
  )
}

function PersonFace({ person }: { person: { full_name: string; avatar_url: string | null } }) {
  const src = toProxyImage(person.avatar_url)
  if (src) return <img src={src} alt="" className="h-11 w-11 rounded-full object-cover" />
  const initials = person.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("")
  return (
    <span aria-hidden className="flex h-11 w-11 items-center justify-center rounded-full bg-muted text-sm font-medium text-ink-muted">
      {initials}
    </span>
  )
}

function Stats({ page }: { page: Page }) {
  const { t } = useTranslation()
  const items = [
    { icon: Library, value: page.stats.courses, label: t("organization.stats.courses", { count: page.stats.courses }) },
    { icon: BookOpen, value: page.stats.lessons, label: t("organization.stats.lessons", { count: page.stats.lessons }) },
    { icon: GraduationCap, value: page.stats.certificates, label: t("organization.stats.certificates", { count: page.stats.certificates }) },
    page.stats.members !== null
      ? { icon: Users, value: page.stats.members, label: t("organization.stats.members", { count: page.stats.members }) }
      : null,
    // Same contract as members: the server sends null below its threshold,
    // and null is "not shown", not zero.
    page.stats.teachers !== null
      ? { icon: UserRound, value: page.stats.teachers, label: t("organization.stats.teachers", { count: page.stats.teachers }) }
      : null,
  ]
    // A zero is not a fact worth a tile: «0 certificates issued» on a new
    // school's page reads as a verdict, not as a beginning.
    .filter((x): x is NonNullable<typeof x> => x !== null && x.value > 0)
  // The course count alone repeats the list of courses right below it.
  if (items.length < 2) return null
  return (
    // Up to five tiles. Four or fewer sit in one row from sm; five need
    // a wider screen for that, and fall into 3 + 2 in between.
    <dl className={cn("mt-10 grid grid-cols-2 gap-4", items.length > 4 ? "sm:grid-cols-3 lg:grid-cols-5" : "sm:grid-cols-4")}>
      {items.map(({ icon: Icon, value, label }) => (
        // The number, then its word: «3 / курса» reads as "3 courses".
        <div key={label} className="flex flex-col-reverse rounded-card border border-edge bg-surface p-4">
          <dt className="mt-1 flex items-center gap-1.5 text-xs text-ink-muted">
            <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            <span>{label}</span>
          </dt>
          <dd className="font-serif text-2xl font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * A closed course, to somebody who is not a member. Until 2026-10-03 this
 * was a card that did nothing when tapped, with one line under the whole
 * grid saying who gives access — a dead end on a phone, where the line sat
 * below the fold. Now the card is a button, and the answer is in a dialog
 * that names the organization and its director, links its website, and
 * offers a member who is simply signed out the way back in.
 */
function LockedCourseCard({ course, page }: { course: LockedCourse; page: Page }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const src = toProxyImage(course.image_url)
  const directors = page.directors.map((d) => d.full_name).join(", ")
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex flex-col overflow-hidden rounded-card border border-edge bg-surface text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <div className="relative aspect-[16/9] w-full bg-muted/40">
          {src ? (
            <img src={src} alt="" className="h-full w-full object-cover opacity-70" />
          ) : (
            <CourseCoverFallback courseId={course.id} title={course.title} size="md" />
          )}
          <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-surface/90 px-2 py-1 text-xs font-medium text-ink">
            <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("organization.byInvitation")}
          </span>
        </div>
        <div className="flex flex-1 flex-col gap-2 p-5">
          <p className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">{course.title}</p>
          {course.description && <p className="line-clamp-3 text-sm text-ink-muted">{course.description}</p>}
          <span className="mt-auto inline-flex items-center gap-1 pt-1 text-sm font-medium text-brand">
            {t("organization.locked.how")}
            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </span>
        </div>
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={course.title}>
        <div className="space-y-4 text-sm">
          <p className="text-ink">
            {directors
              ? t("organization.locked.body", { org: page.public_name, director: directors })
              : t("organization.locked.bodyNoDirector", { org: page.public_name })}
          </p>
          {page.website_url && (
            <a
              href={page.website_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-ink-muted underline-offset-4 hover:text-ink hover:underline"
            >
              <ExternalLink className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("organization.locked.website")}: {websiteLabel(page.website_url)}
            </a>
          )}
          {/* A member who is merely signed out: back here after the sign-in
              (`state.from`, see lib/authRedirect), not to the dashboard. */}
          {!user && (
            <Button asChild variant="outline" size="sm">
              <Link to="/login" state={{ from: `${location.pathname}${location.search}` }}>
                <LogIn className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("organization.locked.signIn")}
              </Link>
            </Button>
          )}
        </div>
      </Modal>
    </>
  )
}

/** «США», not «Соединённые Штаты»: the short form where the locale has one. */
function countryName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "region", style: "short" }).of(code.toUpperCase()) ?? code
  } catch {
    return code
  }
}

function websiteLabel(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "")
  } catch {
    return url
  }
}

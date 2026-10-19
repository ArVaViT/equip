import { useId, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Building2, ChevronDown, ExternalLink, Plus, UserPlus } from "lucide-react"

import { useConfirm } from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { EmptyState, ErrorState } from "@/components/patterns"
import PageSpinner from "@/components/ui/PageSpinner"
import { useAsyncData } from "@/hooks/useAsyncData"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { organizationsService, type AdminOrganization, type OrganizationStatus } from "@/services/organizations"
import { cn } from "@/lib/utils"
import { SchoolSettingsTab } from "../dashboard/SchoolSettingsTab"

const STATUSES: readonly OrganizationStatus[] = ["pending", "approved", "verified", "suspended"]

/**
 * The platform's organizations — created and given a director here, by the
 * platform's own staff only, after the agreement is signed by email. No
 * self-service: an organization on Equip is one somebody decided to admit.
 */
export function OrganizationsTab() {
  const { t } = useTranslation()
  const helpId = useId()
  const [version, setVersion] = useState(0)
  const { data, loading, error } = useAsyncData(() => organizationsService.adminList(), [version])
  const reload = () => setVersion((v) => v + 1)

  if (loading && !data) return <PageSpinner variant="section" />
  if (error || !data)
    return (
      <ErrorState
        title={t("adminOrgs.loadError")}
        action={
          <Button size="sm" variant="outline" onClick={reload}>
            {t("common.tryAgain")}
          </Button>
        }
      />
    )

  return (
    <div className="space-y-6">
      <CreateOrganization onCreated={reload} />
      {data.length === 0 ? (
        <EmptyState icon={<Building2 strokeWidth={1.75} aria-hidden />} title={t("adminOrgs.empty")} />
      ) : (
        <>
          {/* What each status does, said once for every row's select: the
              select saved on change with no word about what changed. */}
          <p id={helpId} className="text-xs text-ink-muted">
            {t("adminOrgs.statusHelp")}
          </p>
          <ul className="space-y-3">
            {data.map((org) => (
              <OrganizationRow key={org.id} org={org} statusHelpId={helpId} onChanged={reload} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/**
 * Whether the organization is on the public showcase, and if not, why.
 * The same three conditions ``GET /organizations`` filters on: verified,
 * somebody directing it, something published.
 */
function ListedLine({ org }: { org: AdminOrganization }) {
  const { t } = useTranslation()
  const reasons = [
    org.status !== "verified" ? t("adminOrgs.listed.notVerified") : null,
    org.director_emails.length === 0 ? t("adminOrgs.listed.noDirector") : null,
    org.published_courses === 0 ? t("adminOrgs.listed.noCourses") : null,
  ].filter((x): x is string => x !== null)
  return (
    <p className="mt-2 text-xs text-ink-muted">
      {reasons.length === 0 ? t("adminOrgs.listed.yes") : t("adminOrgs.listed.no", { reasons: reasons.join(", ") })}
    </p>
  )
}

function CreateOrganization({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation()
  const ids = useId()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [country, setCountry] = useState("")
  const [saving, setSaving] = useState(false)
  const slugOk = /^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug) && slug.length >= 2
  const countryOk = country === "" || /^[A-Za-z]{2}$/.test(country)

  if (!open) {
    return (
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("adminOrgs.create")}
      </Button>
    )
  }
  return (
    <form
      className="grid gap-3 rounded-card border border-edge bg-muted/30 p-4 sm:grid-cols-3"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!slugOk || !countryOk || name.trim().length < 2) return
        setSaving(true)
        try {
          await organizationsService.adminCreate({
            slug,
            public_name: name.trim(),
            country: country ? country.toUpperCase() : undefined,
          })
          toast({ title: t("adminOrgs.created", { name: name.trim() }), variant: "success" })
          setOpen(false)
          setName("")
          setSlug("")
          setCountry("")
          onCreated()
        } catch (err) {
          toast({ title: getErrorDetail(err, t("adminOrgs.failed")), variant: "destructive" })
        } finally {
          setSaving(false)
        }
      }}
    >
      <div className="space-y-1">
        <Label htmlFor={`${ids}-name`} className="text-xs">{t("adminOrgs.name")}</Label>
        <Input id={`${ids}-name`} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${ids}-slug`} className="text-xs">{t("adminOrgs.slug")}</Label>
        <Input
          id={`${ids}-slug`}
          value={slug}
          onChange={(e) => setSlug(e.target.value.toLowerCase())}
          aria-invalid={(slug !== "" && !slugOk) || undefined}
          aria-describedby={`${ids}-slug-hint`}
        />
        <p id={`${ids}-slug-hint`} className="text-xs text-ink-muted">
          {t("adminOrgs.slugHint", { slug: slug || "ucoat" })}
        </p>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${ids}-country`} className="text-xs">{t("adminOrgs.country")}</Label>
        <Input
          id={`${ids}-country`}
          value={country}
          maxLength={2}
          onChange={(e) => setCountry(e.target.value)}
          aria-invalid={!countryOk || undefined}
        />
      </div>
      <div className="flex gap-2 sm:col-span-3">
        <Button type="submit" size="sm" disabled={saving || !slugOk || !countryOk || name.trim().length < 2}>
          {t("adminOrgs.createSave")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  )
}

function OrganizationRow({
  org,
  statusHelpId,
  onChanged,
}: {
  org: AdminOrganization
  statusHelpId: string
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const confirm = useConfirm()
  const ids = useId()
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  /** True when the action landed — a refusal is told in a toast and nothing else moves. */
  const run = async (action: () => Promise<unknown>, success: string): Promise<boolean> => {
    setBusy(true)
    try {
      await action()
      toast({ title: success, variant: "success" })
      onChanged()
      return true
    } catch (err) {
      toast({ title: getErrorDetail(err, t("adminOrgs.failed")), variant: "destructive" })
      return false
    } finally {
      setBusy(false)
    }
  }

  // Suspending hides every course of a school from everyone at once; the one
  // status change that is asked about before it is saved.
  const changeStatus = async (next: OrganizationStatus) => {
    if (next === org.status) return
    if (next === "suspended") {
      const ok = await confirm({
        title: t("adminOrgs.suspendConfirm.title"),
        description: t("adminOrgs.suspendConfirm.body", { name: org.public_name }),
        confirmLabel: t("adminOrgs.suspendConfirm.confirm"),
        tone: "destructive",
      })
      if (!ok) return
    }
    await run(() => organizationsService.adminUpdate(org.id, { status: next }), t("adminOrgs.statusSaved"))
  }

  return (
    <li className="rounded-card border border-edge bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-wrap-safe">{org.public_name}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
            <Link to={`/o/${org.slug}`} className="inline-flex items-center gap-1 underline-offset-4 hover:text-ink hover:underline">
              /o/{org.slug}
              <ExternalLink className="h-3 w-3" strokeWidth={1.75} aria-hidden />
            </Link>
            <span>{t("adminOrgs.members", { count: org.member_count })}</span>
            <span>
              {org.director_emails.length > 0
                ? t("adminOrgs.directors", { list: org.director_emails.join(", ") })
                : t("adminOrgs.noDirector")}
            </span>
          </p>
        </div>
        <div className="w-44">
          <Label htmlFor={`${ids}-status`} className="sr-only">{t("adminOrgs.status")}</Label>
          <Select value={org.status} onValueChange={(v) => void changeStatus(v as OrganizationStatus)} disabled={busy}>
            <SelectTrigger id={`${ids}-status`} size="sm" aria-describedby={statusHelpId}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {t(`adminOrgs.statuses.${s}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <ListedLine org={org} />
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          const value = email.trim()
          if (!value) return
          // The address stays in the field when the server says no — a typo
          // is corrected, not retyped.
          void run(() => organizationsService.adminAppointDirector(org.id, value), t("adminOrgs.directorAppointed", { email: value })).then(
            (ok) => ok && setEmail(""),
          )
        }}
      >
        <div className="min-w-0 flex-1 space-y-1">
          <Label htmlFor={`${ids}-director`} className="text-xs">{t("adminOrgs.appointLabel")}</Label>
          <Input
            id={`${ids}-director`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("adminOrgs.appointPlaceholder")}
          />
        </div>
        <Button type="submit" size="sm" variant="outline" disabled={busy || !email.trim()}>
          <UserPlus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("adminOrgs.appoint")}
        </Button>
      </form>
      {/* What the "School" tab used to hold for platform staff — the name and
          city on this school's documents — opened from the school's own row,
          so one thing is no longer two tabs. */}
      <div className="mt-3 border-t border-edge pt-3">
        <button
          type="button"
          aria-expanded={settingsOpen}
          aria-controls={`${ids}-settings`}
          onClick={() => setSettingsOpen((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", settingsOpen && "rotate-180")}
            strokeWidth={1.75}
            aria-hidden
          />
          {t("adminOrgs.documents")}
        </button>
        <div id={`${ids}-settings`} hidden={!settingsOpen} className="mt-3">
          {/* Mounted on first open only: each row would otherwise ask for its
              settings as the list loads. */}
          {settingsOpen && <SchoolSettingsTab organizationId={org.id} embedded />}
        </div>
      </div>
    </li>
  )
}

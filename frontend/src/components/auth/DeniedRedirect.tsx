import { useEffect, useRef } from "react"
import { Navigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { toast } from "@/lib/toast"

/**
 * Where a signed-in person lands when a route is not for their role.
 *
 * `Gate` used to answer a student on `/teacher` — or a teacher on `/admin`
 * — with a bare redirect: the page they asked for flickered into the one
 * they already had, and nothing said why. That is indistinguishable from a
 * broken link. The redirect stays (the dashboard is the right place to
 * land); the sentence is what was missing. A toast rather than a page: on a
 * «this is not for you» screen there is nothing to do except leave it.
 */
export function DeniedRedirect() {
  const { t } = useTranslation()
  const said = useRef(false)
  useEffect(() => {
    // StrictMode runs effects twice in development; one sentence is enough.
    if (said.current) return
    said.current = true
    toast({ title: t("auth.notice.sectionUnavailable"), variant: "warning" })
  }, [t])
  return <Navigate to="/" replace />
}

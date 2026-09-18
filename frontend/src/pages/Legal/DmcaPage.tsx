import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { SUPPORT_EMAIL } from "@/lib/brand"

/** The six things § 512(c)(3)(A) says a notice must contain. Listed as keys
 *  rather than built in a loop because the locale bundles hold strings, not
 *  arrays — and because a key written out is a key the coverage scanner and a
 *  reader can both find. */
const NOTICE_ITEM_KEYS = [
  "dmca.notice.item1",
  "dmca.notice.item2",
  "dmca.notice.item3",
  "dmca.notice.item4",
  "dmca.notice.item5",
  "dmca.notice.item6",
] as const

/** The four § 512(g)(3) says a counter-notice must contain. */
const COUNTER_ITEM_KEYS = [
  "dmca.counter.item1",
  "dmca.counter.item2",
  "dmca.counter.item3",
  "dmca.counter.item4",
] as const

/**
 * How to complain about copyright here, and how to answer a complaint.
 *
 * Public and unauthenticated, for the same reason the Privacy Policy is: the
 * person who needs this page is a publisher who has never heard of Equip and
 * has no account to sign into. A takedown procedure you can only read from
 * inside the product is not a procedure anybody can use.
 *
 * It is a procedure, not a policy. The obligations themselves — what the
 * platform undertakes, what a teacher warrants when they upload — live in the
 * Terms of Use, and this page links there rather than restating them. Two
 * copies of a rule is two rules, and the second one goes stale first.
 *
 * What is here is the part the Terms cannot carry usefully: the six things
 * § 512(c)(3)(A) says a notice must contain, the four § 512(g)(3) says a
 * counter-notice must contain, where to send either, and the number that
 * closes an account. That last one is the reason this page exists at all.
 * § 512(i)(1)(A) asks a platform to adopt a repeat-infringer policy, *inform*
 * people of it, and implement it, and BMG v. Cox is what happens when the
 * middle or the last of those three is missing.
 *
 * Deliberately not a web form. A notice has to be signed and to carry a
 * statement made under penalty of perjury; a form that collects neither would
 * produce something shaped like a notice that is not one, and would invite
 * people to send it.
 */
export default function DmcaPage() {
  const { t } = useTranslation()


  return (
    <div className="mx-auto w-full max-w-[680px] px-4 py-10 sm:px-6 sm:py-16">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-sm text-ink-muted transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("common.appName")}
      </Link>

      <article className="mt-8">
        <h1 className="font-serif text-2xl leading-tight break-words sm:text-3xl">
          {t("dmca.title")}
        </h1>
        <p className="mt-4 text-ink-muted">{t("dmca.intro")}</p>

        <h2 className="mt-10 font-serif text-xl">{t("dmca.notice.heading")}</h2>
        <p className="mt-3 text-ink-muted">{t("dmca.notice.lead")}</p>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-ink-muted marker:text-ink-muted">
          {NOTICE_ITEM_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ol>
        <p className="mt-4 text-ink-muted">
          {t("dmca.notice.sendTo")}{" "}
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="text-brand underline underline-offset-4"
          >
            {SUPPORT_EMAIL}
          </a>
          {". "}
          {t("dmca.notice.whatWeDo")}
        </p>

        <h2 className="mt-10 font-serif text-xl">{t("dmca.counter.heading")}</h2>
        <p className="mt-3 text-ink-muted">{t("dmca.counter.lead")}</p>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-ink-muted marker:text-ink-muted">
          {COUNTER_ITEM_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ol>
        <p className="mt-4 text-ink-muted">{t("dmca.counter.whatHappens")}</p>

        {/* The number, stated where somebody can read it before it applies to
            them. § 512(i)(1)(A) asks for the policy to be adopted, made known
            and implemented; this paragraph is the middle one. */}
        <h2 className="mt-10 font-serif text-xl">{t("dmca.repeat.heading")}</h2>
        <p className="mt-3 text-ink-muted">{t("dmca.repeat.body")}</p>

        <h2 className="mt-10 font-serif text-xl">{t("dmca.misuse.heading")}</h2>
        <p className="mt-3 text-ink-muted">{t("dmca.misuse.body")}</p>

        <p className="mt-10 border-t border-edge pt-6 text-sm text-ink-muted">
          {t("dmca.seeTerms")}{" "}
          <Link to="/terms" className="text-brand underline underline-offset-4">
            {t("legal.terms")}
          </Link>
          .
        </p>
      </article>
    </div>
  )
}

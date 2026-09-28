import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
import { Plus } from "lucide-react"

import { SUPPORT_EMAIL } from "@/lib/brand"

import { TEXT_VEIL } from "./textVeil"

/**
 * The questions somebody asks before they sign up, answered before they
 * have to.
 *
 * The page says what Equip is. What it did not answer anywhere were the
 * doubts of somebody deciding: is it really free, do I need an account,
 * which languages, what is the certificate worth, can I teach here.
 * BibleProject, MasterClass, Coursera and Duolingo all close on the same
 * short list for the same reason — it is the last thing between a reader
 * and the button. It sits after the film and before the close.
 *
 * ONLY WHAT IS TRUE TODAY. Every answer is a fact of the product as it
 * runs (a course is published only in all four languages; certificates are
 * issued in English and checked at /verify; organisations are set up by
 * the team, not self-served). Questions whose answer is a decision nobody
 * has written down — accreditation, a statement of faith — are left out
 * rather than answered by guess.
 *
 * The inline links are tagged `<ref>` in the catalogues, not `<link>`:
 * `link` is a void element in HTML, and the Trans parser closed it on the
 * spot — the link rendered empty and its words spilled out beside it.
 *
 * `<details>`, not a scripted accordion: it opens with a keyboard and a
 * screen reader for free, needs no JavaScript, and the answers are in the
 * HTML a crawler reads. Closed by default, so on the page it is five lines
 * — «меньше текста» still holds.
 */
export function Faq() {
  const { t } = useTranslation()

  // Literal keys, one call per string — a template key would be invisible to
  // the ``keyCoverage`` check (docs/I18N.md).
  const items: { q: string; a: ReactNode }[] = [
    { q: t("landing.faq.free.q"), a: t("landing.faq.free.a") },
    { q: t("landing.faq.account.q"), a: t("landing.faq.account.a") },
    { q: t("landing.faq.languages.q"), a: t("landing.faq.languages.a") },
    {
      q: t("landing.faq.certificate.q"),
      a: (
        <Trans
          i18nKey="landing.faq.certificate.a"
          components={{ ref: <Link to="/verify" className={LINK} /> }}
        />
      ),
    },
    {
      q: t("landing.faq.teach.q"),
      a: (
        <Trans
          i18nKey="landing.faq.teach.a"
          components={{
            ref: <a href={`mailto:${SUPPORT_EMAIL}`} className={LINK} />,
          }}
        />
      ),
    },
  ]

  return (
    <section aria-labelledby="landing-faq-heading" className="px-5 py-16 lg:py-24">
      <div className={`mx-auto w-full max-w-2xl ${TEXT_VEIL}`}>
        <h2
          id="landing-faq-heading"
          className="font-serif text-3xl font-medium tracking-[-0.025em] text-ink sm:text-4xl"
        >
          {t("landing.faq.heading")}
        </h2>
        <div className="mt-8 divide-y divide-line border-y border-line">
          {items.map((item) => (
            <details key={item.q} className="group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-left font-serif text-lg font-medium leading-snug text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand sm:text-xl [&::-webkit-details-marker]:hidden">
                {item.q}
                <Plus
                  className="h-4 w-4 shrink-0 text-accent transition-transform duration-base ease-out group-open:rotate-45"
                  strokeWidth={1.75}
                  aria-hidden
                />
              </summary>
              <p className="max-w-xl pb-6 pr-10 text-[0.9375rem] leading-relaxed text-ink-muted sm:text-base">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

const LINK =
  "text-ink underline decoration-accent decoration-1 underline-offset-4 hover:decoration-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"

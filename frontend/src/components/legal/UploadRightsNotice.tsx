import { useTranslation } from "react-i18next"

/**
 * One line under an upload control, saying what uploading means.
 *
 * The Teacher & Contributor Agreement makes the uploader responsible for
 * having the right to every file they put into a course, and names what that
 * rules out — a scanned book, a PDF from a file-sharing "free library", another
 * school's curriculum. An agreement accepted once, months ago, on a screen
 * somebody was clicking through is a weak thing to point at afterwards. A line
 * at the moment of the act is a stronger one, and it costs the person nothing:
 * no extra click, no extra checkbox, no dialog in the way.
 *
 * Deliberately not a confirmation step. A second "are you sure" before every
 * upload would be ignored within a week, and an ignored confirmation is worse
 * evidence than a sentence somebody read.
 *
 * A plain anchor rather than a router ``Link``: it opens a new tab either way,
 * so client-side routing buys nothing, and this renders inside leaf editor
 * components that have no business needing a router in their tests.
 */
export function UploadRightsNotice({ className = "" }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <p className={`text-xs leading-relaxed text-ink-muted ${className}`.trim()}>
      {t("legalGate.upload.notice")}{" "}
      <a
        href="/teacher-terms"
        target="_blank"
        rel="noreferrer"
        className="text-brand underline underline-offset-4"
      >
        {t("legal.teacherTerms")}
      </a>
    </p>
  )
}

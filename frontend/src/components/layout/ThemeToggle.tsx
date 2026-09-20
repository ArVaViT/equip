import { Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { useTheme } from "@/context/useTheme"

/**
 * Light or dark, for people who have not signed in.
 *
 * `ThemeProvider` has carried a `toggleTheme` since long before this, and
 * nothing in the interface called it — the theme followed the system and
 * that was the end of it. That is defensible inside the app, where a reader
 * is there to read; it is wrong on a landing page built around a scene that
 * looks quite different on paper than on ink, where "can I see this the
 * other way round" is a fair thing to want answered in one click.
 *
 * Paired with the language switcher in the header, and deliberately the
 * same size and weight: they are the two things a visitor may want to
 * change about the page itself, as opposed to the two things the page wants
 * from them, which are the buttons in the hero.
 */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const { t } = useTranslation()
  const isDark = theme === "dark"

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      // The label names the destination, not the current state: a button
      // that says "dark" while the page is dark reads as a broken toggle to
      // anybody using a screen reader.
      aria-label={isDark ? t("theme.switchToLight") : t("theme.switchToDark")}
      title={isDark ? t("theme.switchToLight") : t("theme.switchToDark")}
    >
      {isDark ? (
        <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      ) : (
        <Moon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      )}
    </Button>
  )
}

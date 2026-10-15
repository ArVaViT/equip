import { useCallback, useState } from "react"
import { generatePassword } from "@/lib/passwordPolicy"

/**
 * The two bits of state every "choose a password" screen needs.
 *
 * There are three of them — register, accept-invite, reset-password — and
 * they were three separate implementations of the same form, which is how
 * they came to disagree: all three enforced six characters while the server
 * enforced twelve, and fixing one would have left the other two lying.
 *
 * `setPassword` receives the generated value.
 */
export function usePasswordAffordances(setPassword: (value: string) => void) {
  const [showPassword, setShowPassword] = useState(false)
  const [passwordGenerated, setPasswordGenerated] = useState(false)

  const toggleShowPassword = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  /**
   * Reveals the password as part of the action: a value nobody chose and
   * nobody can see is a value nobody can save, and the next screen will ask
   * for it again.
   */
  const generate = useCallback(() => {
    setPassword(generatePassword())
    setShowPassword(true)
    setPasswordGenerated(true)
  }, [setPassword])

  /** Call when the person edits the field — the "save it" note goes stale. */
  const noteEdited = useCallback(() => {
    setPasswordGenerated(false)
  }, [])

  return { showPassword, passwordGenerated, toggleShowPassword, generate, noteEdited }
}

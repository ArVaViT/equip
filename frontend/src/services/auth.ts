import { supabase } from "@/lib/supabase"
import type { Session } from "@supabase/supabase-js"

export const authService = {
  async register(
    email: string,
    password: string,
    fullName: string,
    role: "teacher" | "student" = "student",
    /**
     * Locale the user registered in. Carried into Supabase's
     * ``raw_user_meta_data.preferred_locale`` so the
     * ``handle_new_user`` trigger seeds ``profiles.preferred_locale``
     * to the same language the registration form was rendered in.
     * The DB CHECK whitelists this value; passing anything else
     * silently falls back to 'ru' at the trigger level.
     */
    preferredLocale: "en" | "ru" = "ru",
  ): Promise<void> {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
          role,
          preferred_locale: preferredLocale,
        },
      },
    })
    if (error) throw error

    if (data.user && data.user.identities?.length === 0) {
      throw new Error("DUPLICATE_EMAIL")
    }
  },

  async login(email: string, password: string): Promise<{ user: Session["user"]; session: Session }> {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    if (error) throw error
    return data
  },

  async signInWithGoogle(): Promise<{ provider: string; url: string | null }> {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
    if (error) throw error
    return data
  },

  async resetPassword(email: string): Promise<void> {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`,
    })
    if (error) throw error
  },

  async updatePassword(password: string): Promise<void> {
    const { error } = await supabase.auth.updateUser({ password })
    if (error) throw error
  },

  async logout(): Promise<void> {
    const { error } = await supabase.auth.signOut()
    if (error) throw error
  },
}

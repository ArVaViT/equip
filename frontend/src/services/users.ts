import { supabase } from "@/lib/supabase"
import type { MailKind, Profile } from "@/types"

export interface ProfileUpdate {
  full_name?: string
  avatar_url?: string
  time_zone?: string | null
  time_zone_source?: "detected" | "chosen"
  birth_date?: string | null
  country_code?: string | null
  region?: string | null
  city?: string | null
  church?: string | null
  /** Kinds of course mail turned off; see `MAIL_KINDS`. */
  email_off?: MailKind[]
}

export const usersService = {
  /** Only the fields a person may write themselves; `phone`, `role`, `email` are refused by the database. */
  async updateProfile(data: ProfileUpdate): Promise<Profile> {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error("Not authenticated")

    const { data: profile, error } = await supabase
      .from("profiles")
      .update(data)
      .eq("id", session.user.id)
      .select()
      .single()

    if (error) throw error
    return profile as Profile
  },

  /**
   * Turn one kind of course mail on or off, starting from what the row holds
   * now — not from this tab's copy. The unsubscribe link in a mail writes the
   * same list from anywhere; a switch that wrote back a list read an hour ago
   * would quietly turn that back on.
   */
  async setEmailKind(kind: MailKind, on: boolean): Promise<MailKind[]> {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error("Not authenticated")
    const { data: row, error: readError } = await supabase
      .from("profiles")
      .select("email_off")
      .eq("id", session.user.id)
      .single()
    if (readError) throw readError
    const current = ((row?.email_off as MailKind[] | null) ?? []).filter((k) => k !== kind)
    const next = on ? current : [...current, kind]
    const { data: profile, error } = await supabase
      .from("profiles")
      .update({ email_off: next })
      .eq("id", session.user.id)
      .select("email_off")
      .single()
    if (error) throw error
    return ((profile?.email_off as MailKind[] | null) ?? next)
  },

  /**
   * Record the device's zone, unless the person has chosen one.
   *
   * The condition is in the write itself, not only in the caller: a zone
   * chosen on the profile page while this request is in flight must not
   * be overwritten by it, whichever reaches the database first. `null`
   * means the row already holds a chosen zone and nothing was written.
   */
  async reportDetectedTimeZone(zone: string): Promise<Profile | null> {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error("Not authenticated")

    const { data: profile, error } = await supabase
      .from("profiles")
      .update({ time_zone: zone, time_zone_source: "detected" })
      .eq("id", session.user.id)
      .neq("time_zone_source", "chosen")
      .select()
      .maybeSingle()

    if (error) throw error
    return (profile as Profile | null) ?? null
  },
}

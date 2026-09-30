import { supabase } from "@/lib/supabase"
import type { Profile } from "@/types"

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
}

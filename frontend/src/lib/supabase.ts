import { createClient } from "@supabase/supabase-js"

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set")
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    // PKCE, not the implicit default: a redirect back from Google carries a
    // one-time `?code=` bound to a verifier in this browser, instead of the
    // session itself in the fragment — which Datadog RUM and Session Replay
    // recorded with the page URL. See `lib/authLanding.ts`.
    flowType: "pkce",
    // The URL is read, and wiped, by `captureAuthLanding` before monitoring
    // starts, and turned into a session by the landing pages. Left on, the
    // client would race that for the same single-use code.
    detectSessionInUrl: false,
  },
})

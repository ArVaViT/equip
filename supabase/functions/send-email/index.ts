import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";
import { FROM, confirmationUrl, copyFor, localeFor, renderEmail } from "./copy.ts";

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY");
const SEND_EMAIL_HOOK_SECRET = Deno.env.get("SEND_EMAIL_HOOK_SECRET");
const DD_API_KEY = Deno.env.get("DD_API_KEY");
const DD_SITE = Deno.env.get("DD_SITE") ?? "us5.datadoghq.com";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
// Not `SUPABASE_SECRET_KEY`: the platform reserves the `SUPABASE_` prefix
// for its own variables and refuses to store a custom one under it
// ("Env name cannot start with SUPABASE_, skipping"). Hence a project name.
const PROFILE_READ_KEY = Deno.env.get("EQUIP_PROFILE_READ_KEY");
// Where the person should land after GoTrue verifies the token. NOT
// `email_data.site_url` — see `confirmationUrl` for what that turned out to
// be, and what it cost.
const SITE_URL = Deno.env.get("EQUIP_SITE_URL") ?? "https://equipbible.com";

interface EmailHookPayload {
  user: {
    email: string;
    user_metadata: {
      full_name?: string;
      /** Set by ``authService.register``; absent for a Google signup. */
      preferred_locale?: string;
    };
  };
  email_data: {
    token: string;
    token_hash: string;
    redirect_to: string;
    email_action_type: string;
    site_url: string;
    token_new: string;
    token_hash_new: string;
  };
}

async function logToDatadog(level: "info" | "warn" | "error", message: string, extra: Record<string, unknown> = {}) {
  if (!DD_API_KEY) return;
  try {
    await fetch(`https://http-intake.logs.${DD_SITE}/api/v2/logs`, {
      method: "POST",
      headers: { "DD-API-KEY": DD_API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify([{
        ddsource: "send-email",
        service: "send-email",
        hostname: "supabase-edge",
        ddtags: "env:production,project:Equip,managed_by:claude",
        message,
        status: level,
        ...extra,
      }]),
    });
  } catch {
    // swallow — losing a log line is better than failing the email path
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" } });
  }

  let payload: EmailHookPayload;
  try {
    const rawBody = await req.text();

    if (SEND_EMAIL_HOOK_SECRET) {
      const headersObj: Record<string, string> = {};
      req.headers.forEach((v, k) => { headersObj[k] = v; });
      try {
        const wh = new Webhook(SEND_EMAIL_HOOK_SECRET.replace(/^v1,whsec_/, "").replace(/^v1,/, ""));
        payload = wh.verify(rawBody, headersObj) as EmailHookPayload;
      } catch (err) {
        await logToDatadog("error", "webhook signature verification failed", { error: (err as Error).message });
        return new Response(JSON.stringify({ error: "invalid signature" }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
    } else {
      // Fail closed: without the hook secret we cannot verify the caller, so
      // we must NOT process an unsigned body — anyone who knows the URL could
      // otherwise send mail from our verified domain (phishing / reputation
      // damage). In normal operation SEND_EMAIL_HOOK_SECRET is always set.
      await logToDatadog("error", "SEND_EMAIL_HOOK_SECRET missing — refusing unsigned request");
      return new Response(JSON.stringify({ error: "email hook not configured" }), { status: 401, headers: { "Content-Type": "application/json" } });
    }

    const { user, email_data } = payload;
    const emailType = email_data.email_action_type;
    const { locale, source: localeSource } = await localeFor(
      user.email,
      user.user_metadata?.preferred_locale,
      { supabaseUrl: SUPABASE_URL, secretKey: PROFILE_READ_KEY },
    );
    const copy = copyFor(emailType, locale);
    const name = user.user_metadata?.full_name || "";
    const confirmUrl = confirmationUrl({
      supabaseUrl: SUPABASE_URL ?? "",
      siteUrl: SITE_URL,
      tokenHash: email_data.token_hash,
      emailType,
    });

    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM,
        to: [user.email],
        subject: copy.subject,
        html: renderEmail(copy, name, confirmUrl),
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      // Non-blocking by design: a Resend hiccup must not block signup. The
      // failure is logged to Datadog (monitored) rather than surfaced to
      // Supabase Auth as a hook error.
      console.error("Resend delivery failed (non-blocking):", JSON.stringify(data));
      await logToDatadog("error", "resend delivery failed", {
        resend_status: res.status,
        recipient_domain: user.email.split("@")[1],
        email_type: emailType,
      });
    } else {
      await logToDatadog("info", "transactional email sent", {
        recipient_domain: user.email.split("@")[1],
        email_type: emailType,
        locale,
        locale_source: localeSource,
        resend_id: data.id,
      });
    }

    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  } catch (err) {
    console.error("Edge function error (non-blocking):", (err as Error).message);
    await logToDatadog("error", "edge function error", { error: (err as Error).message });
    return new Response(JSON.stringify({ error: (err as Error).message }), { status: 200, headers: { "Content-Type": "application/json" } });
  }
});

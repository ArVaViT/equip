import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY");
const SEND_EMAIL_HOOK_SECRET = Deno.env.get("SEND_EMAIL_HOOK_SECRET");
const DD_API_KEY = Deno.env.get("DD_API_KEY");
const DD_SITE = Deno.env.get("DD_SITE") ?? "us5.datadoghq.com";

interface EmailHookPayload {
  user: {
    email: string;
    user_metadata: {
      full_name?: string;
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

const BRAND = "Equip";
const FROM = "Equip <noreply@equipbible.com>";
const BTN_STYLE = "display: inline-block; background: #2563eb; color: #fff; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; margin: 24px 0;";
const WRAP_STYLE = "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 40px 20px;";
const H1_STYLE = "color: #1a1a2e; font-size: 24px; margin-bottom: 16px;";
const P_STYLE = "color: #4a4a6a; font-size: 16px; line-height: 1.6;";
const SMALL_STYLE = "color: #8888a8; font-size: 13px;";

const EMAIL_TEMPLATES: Record<string, { subject: string; body: (name: string, url: string) => string }> = {
  signup: {
    subject: `Welcome to ${BRAND} — Confirm Your Email`,
    body: (name, url) => `
      <div style="${WRAP_STYLE}">
        <h1 style="${H1_STYLE}">Welcome to ${BRAND}${name ? `, ${name}` : ""}!</h1>
        <p style="${P_STYLE}">Thank you for creating an account. Please confirm your email address to get started.</p>
        <a href="${url}" style="${BTN_STYLE}">Confirm Email</a>
        <p style="${SMALL_STYLE}">If you didn't create this account, you can safely ignore this email.</p>
      </div>
    `,
  },
  recovery: {
    subject: `${BRAND} — Reset Your Password`,
    body: (name, url) => `
      <div style="${WRAP_STYLE}">
        <h1 style="${H1_STYLE}">Reset Your Password</h1>
        <p style="${P_STYLE}">Hi${name ? ` ${name}` : ""},</p>
        <p style="${P_STYLE}">We received a request to reset your password. Click the button below to choose a new one.</p>
        <a href="${url}" style="${BTN_STYLE}">Reset Password</a>
        <p style="${SMALL_STYLE}">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
      </div>
    `,
  },
  magic_link: {
    subject: `${BRAND} — Your Login Link`,
    body: (name, url) => `
      <div style="${WRAP_STYLE}">
        <h1 style="${H1_STYLE}">Login Link</h1>
        <p style="${P_STYLE}">Hi${name ? ` ${name}` : ""}, click the button below to log in.</p>
        <a href="${url}" style="${BTN_STYLE}">Log In</a>
        <p style="${SMALL_STYLE}">This link expires in 1 hour.</p>
      </div>
    `,
  },
  email_change: {
    subject: `${BRAND} — Confirm Email Change`,
    body: (name, url) => `
      <div style="${WRAP_STYLE}">
        <h1 style="${H1_STYLE}">Confirm Email Change</h1>
        <p style="${P_STYLE}">Hi${name ? ` ${name}` : ""}, please confirm your new email address.</p>
        <a href="${url}" style="${BTN_STYLE}">Confirm New Email</a>
        <p style="${SMALL_STYLE}">If you didn't request this change, please contact support.</p>
      </div>
    `,
  },
};

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
    const template = EMAIL_TEMPLATES[emailType] || EMAIL_TEMPLATES.signup;
    const name = user.user_metadata?.full_name || "";
    const confirmUrl = `${email_data.site_url}/auth/confirm?token_hash=${email_data.token_hash}&type=${emailType}`;

    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM,
        to: [user.email],
        subject: template.subject,
        html: template.body(name, confirmUrl),
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

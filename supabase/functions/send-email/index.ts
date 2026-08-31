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

const BRAND = "Equip";
const FROM = "Equip <noreply@equipbible.com>";
const BTN_STYLE = "display: inline-block; background: #2563eb; color: #fff; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; margin: 24px 0;";
const WRAP_STYLE = "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 40px 20px;";
const H1_STYLE = "color: #1a1a2e; font-size: 24px; margin-bottom: 16px;";
const P_STYLE = "color: #4a4a6a; font-size: 16px; line-height: 1.6;";
const SMALL_STYLE = "color: #8888a8; font-size: 13px;";

/**
 * The four transactional emails, in the four languages this platform serves.
 *
 * They used to exist in English only, on a product whose interface, courses
 * and certificates are all translated and whose first audience is Russian-
 * speaking Bible schools. The confirmation email is the very first thing
 * Equip ever says to a person, and it said it in a language they may not
 * read — while the invitation email, sent by the backend, has been
 * translated since August. This closes that gap.
 *
 * The language comes from `user_metadata.preferred_locale`, which
 * `authService.register` already carries into the signup (it is the same
 * value that seeds `profiles.preferred_locale`). A signup that told us
 * nothing gets English, the same fallback the DB trigger uses.
 *
 * Kept as one flat table rather than fetched from the frontend's i18n
 * bundles: an edge function cannot import them, and four short emails
 * duplicated here are cheaper than a build step that keeps them in sync.
 */
type Locale = "en" | "ru" | "de" | "uk";

const LOCALES: readonly Locale[] = ["en", "ru", "de", "uk"] as const;
const DEFAULT_LOCALE: Locale = "en";

/** Anything unrecognised is English — see the note above. */
function resolveLocale(raw: unknown): Locale {
  return typeof raw === "string" && (LOCALES as readonly string[]).includes(raw)
    ? (raw as Locale)
    : DEFAULT_LOCALE;
}

interface Copy {
  subject: string;
  heading: string;
  /** `name` is empty for an account that never gave one. */
  greeting?: (name: string) => string;
  body: string;
  cta: string;
  footer: string;
}

/**
 * "24 hours" is not decoration: `mailer_otp_exp` was raised from 3600 to
 * 86400 on 2026-08-30, because six of the seven password accounts ever made
 * here never confirmed, and a link that died in an hour is the likeliest
 * reason. If that setting changes again, these sentences change with it.
 */
const COPY: Record<string, Record<Locale, Copy>> = {
  signup: {
    en: {
      subject: `Welcome to ${BRAND} — confirm your email`,
      heading: `Welcome to ${BRAND}`,
      body: "Thank you for creating an account. Please confirm your email address to get started.",
      cta: "Confirm email",
      footer: "The link works for 24 hours. If you didn't create this account, you can safely ignore this email.",
    },
    ru: {
      subject: `Добро пожаловать в ${BRAND} — подтвердите почту`,
      heading: `Добро пожаловать в ${BRAND}`,
      body: "Спасибо за регистрацию. Подтвердите адрес почты, чтобы начать.",
      cta: "Подтвердить почту",
      footer: "Ссылка действует сутки. Если аккаунт создавали не вы, просто не отвечайте на это письмо.",
    },
    de: {
      subject: `Willkommen bei ${BRAND} — bestätigen Sie Ihre E-Mail`,
      heading: `Willkommen bei ${BRAND}`,
      body: "Danke für Ihre Registrierung. Bitte bestätigen Sie Ihre E-Mail-Adresse, um loszulegen.",
      cta: "E-Mail bestätigen",
      footer: "Der Link gilt 24 Stunden. Falls Sie dieses Konto nicht erstellt haben, ignorieren Sie diese E-Mail einfach.",
    },
    uk: {
      subject: `Вітаємо в ${BRAND} — підтвердьте пошту`,
      heading: `Вітаємо в ${BRAND}`,
      body: "Дякуємо за реєстрацію. Підтвердьте адресу пошти, щоб почати.",
      cta: "Підтвердити пошту",
      footer: "Посилання діє добу. Якщо акаунт створювали не ви, просто не відповідайте на цей лист.",
    },
  },
  recovery: {
    en: {
      subject: `${BRAND} — reset your password`,
      heading: "Reset your password",
      greeting: (name) => `Hi${name ? ` ${name}` : ""},`,
      body: "We received a request to reset your password. Click the button below to choose a new one.",
      cta: "Reset password",
      footer: "The link works for 24 hours. If you didn't ask for this, you can safely ignore this email.",
    },
    ru: {
      subject: `${BRAND} — сброс пароля`,
      heading: "Сброс пароля",
      greeting: (name) => `Здравствуйте${name ? `, ${name}` : ""}!`,
      body: "Мы получили запрос на смену пароля. Нажмите кнопку ниже, чтобы задать новый.",
      cta: "Задать новый пароль",
      footer: "Ссылка действует сутки. Если вы этого не запрашивали, просто не отвечайте на это письмо.",
    },
    de: {
      subject: `${BRAND} — Passwort zurücksetzen`,
      heading: "Passwort zurücksetzen",
      greeting: (name) => `Hallo${name ? ` ${name}` : ""},`,
      body: "Wir haben eine Anfrage zum Zurücksetzen Ihres Passworts erhalten. Klicken Sie unten, um ein neues zu wählen.",
      cta: "Passwort zurücksetzen",
      footer: "Der Link gilt 24 Stunden. Falls Sie das nicht angefragt haben, ignorieren Sie diese E-Mail einfach.",
    },
    uk: {
      subject: `${BRAND} — скидання пароля`,
      heading: "Скидання пароля",
      greeting: (name) => `Вітаємо${name ? `, ${name}` : ""}!`,
      body: "Ми отримали запит на зміну пароля. Натисніть кнопку нижче, щоб задати новий.",
      cta: "Задати новий пароль",
      footer: "Посилання діє добу. Якщо ви цього не запитували, просто не відповідайте на цей лист.",
    },
  },
  magic_link: {
    en: {
      subject: `${BRAND} — your login link`,
      heading: "Your login link",
      greeting: (name) => `Hi${name ? ` ${name}` : ""},`,
      body: "Click the button below to sign in.",
      cta: "Sign in",
      footer: "The link works for 24 hours.",
    },
    ru: {
      subject: `${BRAND} — ссылка для входа`,
      heading: "Ссылка для входа",
      greeting: (name) => `Здравствуйте${name ? `, ${name}` : ""}!`,
      body: "Нажмите кнопку ниже, чтобы войти.",
      cta: "Войти",
      footer: "Ссылка действует сутки.",
    },
    de: {
      subject: `${BRAND} — Ihr Anmeldelink`,
      heading: "Ihr Anmeldelink",
      greeting: (name) => `Hallo${name ? ` ${name}` : ""},`,
      body: "Klicken Sie unten, um sich anzumelden.",
      cta: "Anmelden",
      footer: "Der Link gilt 24 Stunden.",
    },
    uk: {
      subject: `${BRAND} — посилання для входу`,
      heading: "Посилання для входу",
      greeting: (name) => `Вітаємо${name ? `, ${name}` : ""}!`,
      body: "Натисніть кнопку нижче, щоб увійти.",
      cta: "Увійти",
      footer: "Посилання діє добу.",
    },
  },
  email_change: {
    en: {
      subject: `${BRAND} — confirm your new email`,
      heading: "Confirm your new email",
      greeting: (name) => `Hi${name ? ` ${name}` : ""},`,
      body: "Please confirm your new email address.",
      cta: "Confirm new email",
      footer: "If you didn't request this change, contact us — somebody else may have access to your account.",
    },
    ru: {
      subject: `${BRAND} — подтвердите новую почту`,
      heading: "Подтвердите новую почту",
      greeting: (name) => `Здравствуйте${name ? `, ${name}` : ""}!`,
      body: "Подтвердите новый адрес почты.",
      cta: "Подтвердить новую почту",
      footer: "Если вы этого не запрашивали, напишите нам — возможно, к вашему аккаунту есть чужой доступ.",
    },
    de: {
      subject: `${BRAND} — neue E-Mail bestätigen`,
      heading: "Neue E-Mail bestätigen",
      greeting: (name) => `Hallo${name ? ` ${name}` : ""},`,
      body: "Bitte bestätigen Sie Ihre neue E-Mail-Adresse.",
      cta: "Neue E-Mail bestätigen",
      footer: "Falls Sie diese Änderung nicht angefragt haben, melden Sie sich bei uns — möglicherweise hat jemand anderes Zugriff auf Ihr Konto.",
    },
    uk: {
      subject: `${BRAND} — підтвердьте нову пошту`,
      heading: "Підтвердьте нову пошту",
      greeting: (name) => `Вітаємо${name ? `, ${name}` : ""}!`,
      body: "Підтвердьте нову адресу пошти.",
      cta: "Підтвердити нову пошту",
      footer: "Якщо ви цього не запитували, напишіть нам — можливо, до вашого акаунта має доступ хтось інший.",
    },
  },
};

function renderEmail(copy: Copy, name: string, url: string): string {
  const heading = copy.greeting ? copy.heading : `${copy.heading}${name ? `, ${name}` : ""}`;
  const greeting = copy.greeting ? `<p style="${P_STYLE}">${copy.greeting(name)}</p>` : "";
  return `
      <div style="${WRAP_STYLE}">
        <h1 style="${H1_STYLE}">${heading}</h1>
        ${greeting}
        <p style="${P_STYLE}">${copy.body}</p>
        <a href="${url}" style="${BTN_STYLE}">${copy.cta}</a>
        <p style="${SMALL_STYLE}">${copy.footer}</p>
      </div>
    `;
}

/** Falls back to signup for an action type we have no copy for. */
function copyFor(emailType: string, locale: Locale): Copy {
  const byLocale = COPY[emailType] ?? COPY.signup;
  return byLocale[locale] ?? byLocale[DEFAULT_LOCALE];
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
    const locale = resolveLocale(user.user_metadata?.preferred_locale);
    const copy = copyFor(emailType, locale);
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

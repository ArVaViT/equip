/**
 * The words these emails are made of, and the rules for choosing a language.
 *
 * Split out of `index.ts` so it can be tested: the function itself imports
 * `Deno.env` and the Supabase edge runtime at module scope, which no test
 * runner here can load. Everything in this file is pure except `localeFor`,
 * whose one impure edge — the profile lookup — is injected.
 */

export const BRAND = "Equip";
export const FROM = "Equip <noreply@equipbible.com>";
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
export type Locale = "en" | "ru" | "de" | "uk";

export const LOCALES: readonly Locale[] = ["en", "ru", "de", "uk"] as const;
export const DEFAULT_LOCALE: Locale = "en";

/** The value if we serve that language, `null` otherwise. */
export function knownLocale(raw: unknown): Locale | null {
  return typeof raw === "string" && (LOCALES as readonly string[]).includes(raw)
    ? (raw as Locale)
    : null;
}

/**
 * The language to write in, and where it came from.
 *
 * `user_metadata.preferred_locale` only exists for accounts created through
 * this app's own registration form. Measured against production on
 * 2026-08-31: of 38 accounts, six carry it — and of the thirteen whose
 * profile says Russian, exactly one. Everybody else signed in with Google,
 * which carries no language at all, or registered before the form started
 * sending it. Reading metadata alone would therefore have written English to
 * twelve of the thirteen Russian speakers: a translation that misses almost
 * everyone it was for.
 *
 * So metadata first (it is the freshest thing we have, and during signup the
 * profile row may not exist yet), then the profile, then English.
 *
 * Best-effort by design: a failed lookup must not stop the email. The
 * request is given three seconds and every failure falls through to the
 * next source.
 */
export interface ProfileLookup {
  supabaseUrl?: string;
  secretKey?: string;
  /** Injected so tests can drive the failure paths without a network. */
  fetchImpl?: typeof fetch;
}

export async function localeFor(
  email: string,
  metadataLocale: unknown,
  lookup: ProfileLookup = {},
): Promise<{ locale: Locale; source: "metadata" | "profile" | "default" }> {
  const fromMetadata = knownLocale(metadataLocale);
  if (fromMetadata) return { locale: fromMetadata, source: "metadata" };

  const { supabaseUrl, secretKey, fetchImpl = fetch } = lookup;
  if (!supabaseUrl || !secretKey) return { locale: DEFAULT_LOCALE, source: "default" };

  try {
    const url = `${supabaseUrl}/rest/v1/profiles?select=preferred_locale&email=eq.${encodeURIComponent(email)}`;
    const res = await fetchImpl(url, {
      headers: { apikey: secretKey, Authorization: `Bearer ${secretKey}` },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return { locale: DEFAULT_LOCALE, source: "default" };
    const rows = (await res.json()) as Array<{ preferred_locale?: string }>;
    const fromProfile = knownLocale(rows[0]?.preferred_locale);
    if (fromProfile) return { locale: fromProfile, source: "profile" };
  } catch {
    // Swallowed on purpose: an unreachable PostgREST is a reason to write in
    // English, never a reason to withhold somebody's confirmation link.
  }
  return { locale: DEFAULT_LOCALE, source: "default" };
}

export interface Copy {
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
export const COPY: Record<string, Record<Locale, Copy>> = {
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

export function renderEmail(copy: Copy, name: string, url: string): string {
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
export function copyFor(emailType: string, locale: Locale): Copy {
  const byLocale = COPY[emailType] ?? COPY.signup;
  return byLocale[locale] ?? byLocale[DEFAULT_LOCALE];
}



/**
 * The link a person actually clicks — and the defect this file exists to end.
 *
 * It used to be built as `${email_data.site_url}/auth/confirm?token_hash=…`,
 * on the assumption that `site_url` is the site. It is not: GoTrue sends the
 * project's auth API base, so every confirmation email ever sent by this
 * platform carried
 *
 *   https://<ref>.supabase.co/auth/v1/auth/confirm?token_hash=…
 *
 * — a path that does not exist. Clicking it returned
 * `{"message":"No API key found in request"}`. Verified by hand on
 * 2026-08-31 against a real email: six of the seven accounts ever created
 * with a password never confirmed, and this is why. Not spam filtering, not
 * the one-hour expiry: the button did not work.
 *
 * The correct link is GoTrue's own `verify` endpoint, which needs no API key
 * and 303s to `redirect_to` with the session in the fragment — which is
 * exactly what `/auth/confirm` on the frontend is already waiting for.
 *
 * `siteUrl` comes from configuration rather than from the hook payload,
 * because the payload's own idea of the site is what caused this.
 */
export function confirmationUrl(opts: {
  supabaseUrl: string;
  siteUrl: string;
  tokenHash: string;
  emailType: string;
}): string {
  const base = opts.supabaseUrl.replace(/\/+$/, "");
  const redirectTo = `${opts.siteUrl.replace(/\/+$/, "")}/auth/confirm`;
  const params = new URLSearchParams({
    token: opts.tokenHash,
    type: opts.emailType,
    redirect_to: redirectTo,
  });
  return `${base}/auth/v1/verify?${params.toString()}`;
}

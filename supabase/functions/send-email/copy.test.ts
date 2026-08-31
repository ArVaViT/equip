/**
 * Tests for the only part of the email path that can be tested off-runtime.
 *
 * There were none before: `index.ts` reads `Deno.env` and the edge runtime at
 * module scope, so nothing could import it, and the emails it sends were
 * never exercised anywhere. That is how they stayed English-only on a
 * four-language product, and how "this link expires in 1 hour" outlived the
 * setting it described.
 *
 * Run: deno test supabase/functions/send-email/copy.test.ts
 */
import { assert, assertEquals, assertStringIncludes } from "jsr:@std/assert@1";
import {
  COPY,
  LOCALES,
  confirmationUrl,
  copyFor,
  knownLocale,
  localeFor,
  renderEmail,
} from "./copy.ts";

const TYPES = ["signup", "recovery", "magic_link", "email_change"] as const;
const LINK = "https://equipbible.com/auth/confirm?token_hash=abc&type=signup";

Deno.test("every email exists in every language", () => {
  for (const type of TYPES) {
    for (const locale of LOCALES) {
      const copy = COPY[type][locale];
      assert(copy, `${type}/${locale} отсутствует`);
      for (const field of ["subject", "heading", "body", "cta", "footer"] as const) {
        assert(copy[field].trim().length > 0, `${type}/${locale}.${field} пустое`);
      }
    }
  }
});

Deno.test("every email renders with the link and the reader's name", () => {
  for (const type of TYPES) {
    for (const locale of LOCALES) {
      const html = renderEmail(copyFor(type, locale), "Вадим", LINK);
      assertStringIncludes(html, LINK);
      assertStringIncludes(html, "Вадим");
      assert(!html.includes("undefined"), `${type}/${locale}: undefined в письме`);
    }
  }
});

Deno.test("an account with no name still gets a sensible email", () => {
  for (const locale of LOCALES) {
    const html = renderEmail(copyFor("signup", locale), "", LINK);
    assert(!html.includes(", <"), `${locale}: висящая запятая без имени`);
    assert(!html.includes("undefined"));
  }
});

Deno.test("the link lifetime in the copy matches mailer_otp_exp", () => {
  // `mailer_otp_exp` was raised to 86400 on 2026-08-30. Before that these
  // said "1 hour", and after it they would have been quietly wrong.
  const promises: Record<string, string> = {
    en: "24 hours",
    ru: "сутки",
    de: "24 Stunden",
    uk: "добу",
  };
  for (const locale of LOCALES) {
    for (const type of ["signup", "recovery", "magic_link"] as const) {
      assertStringIncludes(COPY[type][locale].footer, promises[locale]);
    }
  }
});

Deno.test("an unknown action type falls back instead of throwing", () => {
  const copy = copyFor("reauthentication", "ru");
  assertEquals(copy.subject, COPY.signup.ru.subject);
});

Deno.test("knownLocale accepts only what we serve", () => {
  assertEquals(knownLocale("ru"), "ru");
  assertEquals(knownLocale("es"), null);
  assertEquals(knownLocale(undefined), null);
  assertEquals(knownLocale(42), null);
});

function lookupReturning(body: unknown, status = 200) {
  return {
    supabaseUrl: "https://project.supabase.co",
    secretKey: "sb_secret_test",
    fetchImpl: ((_url: string | URL | Request) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        }),
      )) as typeof fetch,
  };
}

Deno.test("signup metadata wins, and costs no request", async () => {
  const exploding = {
    supabaseUrl: "https://project.supabase.co",
    secretKey: "sb_secret_test",
    fetchImpl: (() => {
      throw new Error("профиль не должен запрашиваться");
    }) as unknown as typeof fetch,
  };
  const got = await localeFor("a@example.com", "ru", exploding);
  assertEquals(got, { locale: "ru", source: "metadata" });
});

Deno.test("without metadata the profile decides", async () => {
  // This is the common case, not the rare one: measured on production
  // 2026-08-31, only 6 of 38 accounts carry the locale in metadata, and of
  // the 13 whose profile says Russian, exactly one does.
  const got = await localeFor("a@example.com", undefined, lookupReturning([{ preferred_locale: "uk" }]));
  assertEquals(got, { locale: "uk", source: "profile" });
});

Deno.test("nothing anywhere means English", async () => {
  assertEquals(
    await localeFor("a@example.com", undefined, lookupReturning([])),
    { locale: "en", source: "default" },
  );
  assertEquals(
    await localeFor("a@example.com", undefined, lookupReturning([{ preferred_locale: "es" }])),
    { locale: "en", source: "default" },
  );
});

Deno.test("a broken lookup never withholds the email", async () => {
  assertEquals(
    await localeFor("a@example.com", undefined, lookupReturning({}, 500)),
    { locale: "en", source: "default" },
  );

  const offline = {
    supabaseUrl: "https://project.supabase.co",
    secretKey: "sb_secret_test",
    fetchImpl: (() => Promise.reject(new Error("network down"))) as typeof fetch,
  };
  assertEquals(await localeFor("a@example.com", undefined, offline), {
    locale: "en",
    source: "default",
  });
});

Deno.test("no credentials configured means English, not a crash", async () => {
  assertEquals(await localeFor("a@example.com", undefined, {}), {
    locale: "en",
    source: "default",
  });
});

Deno.test("an email address with a plus sign is escaped into the query", async () => {
  let requested = "";
  const capture = {
    supabaseUrl: "https://project.supabase.co",
    secretKey: "sb_secret_test",
    fetchImpl: ((url: string | URL | Request) => {
      requested = String(url);
      return Promise.resolve(
        new Response(JSON.stringify([{ preferred_locale: "de" }]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }) as typeof fetch,
  };
  await localeFor("vadym+equip@example.com", undefined, capture);
  // An unescaped '+' reads as a space to PostgREST and matches nobody.
  assertStringIncludes(requested, "vadym%2Bequip%40example.com");
});


Deno.test("the confirmation link points at GoTrue's verify endpoint", () => {
  // The old link was `${email_data.site_url}/auth/confirm?token_hash=…`, and
  // `site_url` is the auth API base, not the site — so every email ever sent
  // carried https://<ref>.supabase.co/auth/v1/auth/confirm, a path that does
  // not exist. Clicking it answered "No API key found in request".
  const url = confirmationUrl({
    supabaseUrl: "https://project.supabase.co",
    siteUrl: "https://equipbible.com",
    tokenHash: "abc123",
    emailType: "signup",
  });
  const parsed = new URL(url);
  assertEquals(parsed.origin, "https://project.supabase.co");
  assertEquals(parsed.pathname, "/auth/v1/verify");
  assertEquals(parsed.searchParams.get("token"), "abc123");
  assertEquals(parsed.searchParams.get("type"), "signup");
  assertEquals(parsed.searchParams.get("redirect_to"), "https://equipbible.com/auth/confirm");
  assert(!url.includes("/auth/v1/auth/"), "старый несуществующий путь вернулся");
});

Deno.test("the link survives trailing slashes in configuration", () => {
  const url = confirmationUrl({
    supabaseUrl: "https://project.supabase.co/",
    siteUrl: "https://equipbible.com/",
    tokenHash: "abc123",
    emailType: "recovery",
  });
  assert(!url.includes("//auth/v1"), `двойной слэш в пути: ${url}`);
  assertEquals(
    new URL(url).searchParams.get("redirect_to"),
    "https://equipbible.com/auth/confirm",
  );
});

Deno.test("a token with URL-special characters is escaped", () => {
  const url = confirmationUrl({
    supabaseUrl: "https://project.supabase.co",
    siteUrl: "https://equipbible.com",
    tokenHash: "a+b/c=d&e",
    emailType: "magiclink",
  });
  assertEquals(new URL(url).searchParams.get("token"), "a+b/c=d&e");
});

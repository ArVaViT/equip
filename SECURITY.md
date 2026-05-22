# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| `main`  | :white_check_mark: |

Only the latest code on the `main` branch receives security fixes. There are no
tagged releases with long-term support yet.

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email **supportequip@gmail.com** with:

1. A description of the vulnerability.
2. Steps to reproduce (or a proof-of-concept).
3. The impact you believe it has.

You will receive an acknowledgement within **72 hours** and a more detailed
response within **7 days** indicating next steps.

## Disclosure timeline

We follow a coordinated disclosure process:

1. Reporter emails the maintainer.
2. Maintainer confirms receipt within 72 hours.
3. Maintainer investigates and develops a fix (target: 30 days).
4. Fix is merged and deployed; a security advisory is published on GitHub.
5. Reporter is credited (unless they prefer to remain anonymous).

## Scope

The following are in scope:

- Backend API (`backend/`) — authentication bypass, injection, privilege
  escalation, data leaks.
- Frontend (`frontend/`) — XSS, CSRF, open redirects.
- Supabase RLS policies (`supabase/migrations/`) — policy gaps that expose
  data across tenants or roles.
- CI/CD pipelines (`.github/workflows/`) — secret leakage, supply-chain
  issues.

The following are **out of scope**:

- Denial-of-service attacks against the hosted demo.
- Social engineering of maintainers or users.
- Vulnerabilities in third-party services (Supabase, Vercel) — report those
  directly to the respective vendor.

## Security best practices in this project

- Supabase RLS is enabled on every table; new migrations must include RLS
  policies.
- All user-facing string fields have `max_length` constraints via Pydantic.
- HTML content is sanitized server-side on create/update.
- CORS is locked to known origins.
- Production API docs (`/docs`, `/redoc`) are disabled.
- `pip-audit` and `npm audit` run in CI on every push and PR.

Thank you for helping keep Equip and its users safe.

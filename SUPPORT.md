# Getting help with Equip

We try to make sure every question lands in a place where someone can actually answer it. Pick the channel that matches what you need.

## I have a question about how to use Equip

Open a thread in [**GitHub Discussions**](https://github.com/ArVaViT/equip/discussions). Discussions are the home for usage questions, "what's the right way to…" conversations, and feedback that isn't a bug report.

Useful categories:

- **Q&A** &mdash; a specific question with a yes/no or how-to answer.
- **Ideas** &mdash; a feature you'd like to see, especially with the ministry context that motivated it.
- **Show and tell** &mdash; a deployment, a course you're running on Equip, a screenshot of how your school uses it.

A maintainer aims to respond within a few days. Discussions are public, so other users facing the same question will find your thread later &mdash; please don't open duplicates as private messages.

## I found a bug

Open a [**bug report issue**](https://github.com/ArVaViT/equip/issues/new?template=bug_report.yml). Please include:

- What you were trying to do.
- What you expected to happen.
- What actually happened (a screenshot or browser-console snippet goes a long way).
- Whether it reproduces every time or only sometimes.
- Your environment (browser + version, deployment target, whether self-hosted or on equipbible.com).

## I want to request a feature

Open a [**feature request issue**](https://github.com/ArVaViT/equip/issues/new?template=feature_request.yml). The most useful feature requests describe the underlying problem (what teaching or ministry workflow is currently hard) rather than jumping straight to a UI design &mdash; that gives us room to find the simplest solution.

## I want to report a security vulnerability

**Please do not open a public issue.** Follow the disclosure path in [SECURITY.md](SECURITY.md) instead. We respond within a few business days and treat disclosure reports as confidential.

## I want to contribute code or docs

Start with [**CONTRIBUTING.md**](CONTRIBUTING.md). It covers local setup, commit conventions, the PR workflow, and how AI-assisted contributions are credited (see also [AGENTS.md](AGENTS.md)).

If you're looking for somewhere to start, the [`good first issue` label](https://github.com/ArVaViT/equip/labels/good%20first%20issue) lists scoped issues a new contributor can pick up without needing the full architectural context. Comment on the issue to claim it before opening a PR &mdash; that avoids two people working on the same thing.

## I'm a nonprofit considering Equip for our school

Open a [**Discussion**](https://github.com/ArVaViT/equip/discussions/new?category=q-a) describing your school, your rough scale (number of students, courses, languages), and your hosting comfort level (do you want to run it yourselves, or use the free tiers of Vercel + Supabase?). We answer those personally &mdash; "is Equip a fit for us?" is one of the most valuable questions to surface, both for you and for the roadmap.

## Response times, honestly

Equip is maintained primarily by one person, with growing contributor support. Realistic expectations:

| Channel | Typical first response |
|---|---|
| Security disclosure (SECURITY.md) | 1&ndash;3 business days |
| Bug report on a deployed feature | 2&ndash;5 business days |
| Discussion question | 3&ndash;7 days |
| Feature request | Triaged within a week; implementation timing varies |
| Pull request review | 2&ndash;5 business days for small PRs |

If something is urgent and time-sensitive (the production deployment at equipbible.com is broken, a security issue is being actively exploited), email arvavitcorp@gmail.com directly.

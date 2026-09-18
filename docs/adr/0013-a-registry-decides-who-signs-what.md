# ADR-0013: A registry decides who signs what, and which edits cost a signature

- **Status**: Accepted (2026-09-17)
- **Date**: 2026-09-17
- **Decision-makers**: VA

## Context

The platform published two documents — a privacy policy and terms of use — in
two of the four languages the interface serves, at a version bumped by hand.
Three separate facts had no home in the code:

1. **Who has to sign what.** Both documents were asked of everybody. There was
   nothing a teacher had to accept that a student did not, even though a
   teacher can publish material to other people, read other people's work, and
   decide what a certificate says.
2. **Whether an edit is material.** Bumping `LEGAL_DOCUMENTS["privacy"]` was the
   only lever, and it brought every account back to a blocking gate. So the
   choice at the keyboard was: re-sign the whole platform over a typo, or edit
   the file and leave the version alone. Production shows the second choice was
   made: two different `content_sha256` values exist for each document at
   version 1.0, because the texts were edited under people who had accepted
   them. The acceptance rows are still individually true — each names the hash
   of the text it was handed — but "accepted privacy 1.0" stopped identifying
   one text, which is the single question a consent record exists to answer.
3. **Which languages a document must exist in.** Two, in a four-language
   product, with a runtime fallback that handed a German reader the English
   text and a line apologising for it.

At the same time the documents themselves were thin where it costs most: no
licence over uploaded material (while the platform stores it, caches it,
reformats it and machine-translates it through Gemini), no warranty from the
uploader that they had the right to upload, no indemnity, no notice-and-
takedown procedure, no dispute clause, and a privacy policy that described
less than the software does — it did not mention that Datadog RUM records 100 %
of sessions with Session Replay, that Vercel request logs carry IP addresses
for 15 days, or that course content is sent to Google for translation.

## Decision

**Move all three facts into one registry, `backend/app/legal/registry.py`, and
make each of them a field rather than a judgement.**

```python
Revision(version, effective, consent)     # consent: does this version need signing?
DocumentSpec(slug, required_for, revisions)   # required_for: a set of roles
```

- `required_for` is a set of roles. `teacher-terms` — a new Teacher &
  Contributor Agreement — names `teacher`, `director` and `admin`, and nobody
  else is ever shown it. `privacy` and `terms` name everybody. `providers` names
  nobody: it is a page the policy points at, read and never signed.
- `consent` on a revision is the mechanism the whole ADR is for. A version that
  changes what somebody is agreeing to sets it `True` and brings everybody back
  to the gate. A correction, a clarification, a shortened retention window or a
  new right sets it `False`: it is published, the reader is **told**, and nobody
  signs again. `outstanding_for()` looks back to the most recent `consent=True`
  revision rather than to the newest one, so an acceptance at or after that
  point stays current under any number of later corrections.
- What counts as material is defined **inside each document's own text**, in its
  "Changes" section, as a list. The flag in the registry is the editorial
  decision; the document is the rule it was made against. Neither alone is
  enough: a flag with no published rule is a mood, and a rule with no flag is a
  promise nothing enforces.
- `LOCALES` is four. A document missing one of them raises at read time — a
  broken deployment, not a fallback.

The documents were rewritten to match, in all four languages, with the English
text named as governing.

## Consequences

**Easier.**

- A typo fix costs nobody a click, and the project can therefore afford to fix
  typos. The previous arrangement quietly taught the opposite lesson.
- "Does this person owe anything" is one server answer, computed from the role
  on their profile row. That is also how a promotion reaches a tab that never
  re-reads its own profile: `AuthContext` deliberately does not refetch the
  profile on token refresh or on focus, so a newly promoted teacher's client
  would otherwise not know. The legal status route knows, because it asks the
  database.
- Adding a document is a registry entry plus four files.

**Harder.**

- Every document now has to be written four times, by hand. The course
  translation pipeline is deliberately not used: it is tuned for lesson prose,
  it parks rows for review, and a binding document that says something slightly
  different in Ukrainian because a machine was having an off day is a worse
  failure than a missing translation.
- The fingerprint table grows by four rows per version instead of two.

**Deliberately deferred.**

- **No legal entity.** The documents say "Equip is a project, not a company".
  Limitation-of-liability and indemnity clauses are written anyway, and they are
  worth having, but with no company behind them the person they ultimately point
  at is the maintainer personally. That is a business decision recorded
  elsewhere, not an engineering one, and it is unchanged here.
- **No registered DMCA agent.** The terms describe the notice-and-counter-notice
  procedure and the platform follows it, which is worth doing on its own. The
  § 512(c) safe harbour additionally requires an agent registered with the U.S.
  Copyright Office; that registration has not been made.
- **No self-service export or delete.** The privacy policy now says so in those
  words rather than promising a button that does not exist.

## Alternatives considered

**Keep one version number and decide case by case.** This is what was happening,
and production shows where it goes: the version stops identifying a text. A
hand-maintained `LEGAL_DOCUMENTS` dict cannot distinguish "nobody needs to
re-sign" from "nobody was asked to re-sign".

**Semantic versions with a convention (major = re-sign, minor = notice).**
Tempting, and rejected: the convention lives in a person's memory, a `2.0` can
be typed where `1.2` was meant, and nothing fails. An explicit boolean cannot be
typed by accident and is asserted by tests, including a mutation test that flips
it and requires the answers to change.

**A `legal_documents` table in the database.** Rejected for the reason the
original module records: the server has to be able to reproduce the exact bytes
an acceptance hashed. Files in the deployment artefact are reproducible from a
git SHA; rows in a database are editable by whoever can reach the database,
which is the failure mode this whole area exists to prevent.

**Put the teacher agreement inside the terms of use.** Rejected: it would make
every student re-sign whenever something that only concerns teachers changed —
exactly the cost this ADR is about removing.

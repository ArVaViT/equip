# Privacy Policy

**Version 2.0 · in force from 17 September 2026**

Equip is a platform for Bible schools. This document sets out what the platform
stores, why, who can see it, how long it is kept, and how to take it away or
delete it. It is written for a person rather than a lawyer.

It is longer than the version before it, and on purpose: the previous version
described less than the platform actually does. Everything named here is
something the software does today, checked against the code and against the
running system.

## Who we are

Equip is a non-commercial project, not a company. There are people behind the
platform rather than a legal entity, and questions go to
**supportequip@gmail.com**. We say this plainly because it is worth knowing
before you sign up: in a dispute there is nobody to escalate to except us.

**Who decides what happens to your data.** For your account and for the running
of the platform, that is us — in data-protection language, we are the
controller, and supportequip@gmail.com is the address for every question,
request or complaint about it. For your coursework, your marks and your
progress, the school teaching you decides: the school is the controller and we
act on its instructions, which is what the [School Agreement](/school-agreement)
sets out. In practice write to us either way and we will sort out which of us
answers.

**If we get it wrong.** Tell us first — we would rather fix it than be told
about it by somebody else. But if you are in the European Economic Area or the
United Kingdom you also have the right to complain to the data-protection
authority of the country you live in, and you do not need our permission or our
agreement to do it.

## What we store

**What you enter yourself.** Name, email address, profile photograph, preferred
language. Your name is printed on certificates and grade sheets, so it should
be the name you want to be recorded under.

**What you do on a course.** Chapters read, quiz answers, work submitted, marks
and teacher feedback, certificates earned, and the declarations you make about
your own work.

**What teachers upload.** Files, texts and images added to a course by a teacher
or a director, and the machine translations of them.

**Records that something happened.** An audit record of actions taken on the
platform — who created a course, who changed a mark, who enrolled whom. Since
September 2026 this record holds **no IP address and no browser identifier**;
it holds who, what, and when.

**IP addresses, at two moments.** When you accept a document like this one, and
when you hand in work with a declaration attached. The IP is stored precisely
so that an acceptance and a declaration can be shown to have actually been
made. It is used for nothing else, and nothing else you do on the platform
writes your IP into our database.

**Your sign-in sessions.** Our authentication provider (Supabase) records, for
each active session, the **IP address and the browser User-Agent** it was
started from. That is part of how sign-in works, not something we switch on. A
session record lives as long as the session does; signing out ends it.

## What the platform records about how you use it

This section describes measurement, and it is the part most policies leave
vague. Ours does not, because both of these are turned all the way up.

**Frontend session recording (Datadog Real User Monitoring).** Every session is
recorded — **100 % of sessions, and 100 % of them with Session Replay**, which
reconstructs what happened in the browser as a replayable picture of the page.
Concretely:

- **Text that was visible on your screen is in the recording.** Headings,
  buttons, menus, the lesson you had open, a mark shown on a page — all of it.
- **Text you typed into a field is not.** Every input, textarea and
  content-editable area is masked before anything leaves the browser
  (`mask-user-input`), so quiz answers, essay text, search boxes and passwords
  are replaced by placeholders in the recording. Once your answer is *displayed
  back to you* on a results page, however, it is displayed text, and displayed
  text is recorded.
- **Also recorded:** the pages you visited and in what order, clicks, scrolls
  and typing *events* (that a key was pressed, not what it was), how long things
  took to load, JavaScript errors, and the network requests the page made.
- **You are identified in it.** When you are signed in, the session carries your
  user id, your email address and your name, so that an error report can be
  traced to the person who hit it.
- It is for finding and fixing breakage. It is not sold, not shared with
  advertisers, and not used to build a profile of you.

**Server and request logs.** Requests to the site and to the API pass through
our hosting provider (Vercel) and are streamed to Datadog. Those request logs
**contain the IP address** the request came from, along with the path, the
response code and timing. This is infrastructure logging rather than something
we chose to record about you, but it is your IP and you should know it is there.
They are kept for **15 days** and then deleted by expiry.

**No advertising, no tracking pixels, no third-party analytics.** There is no ad
network, no marketing tag, no cross-site tracking, and no tracking pixel in the
email the platform sends. The measurement described above is the whole of it.

**Cookies and local storage.** The platform sets what it needs to keep you
signed in and to remember your language and a few screen preferences. There are
no advertising or cross-site cookies.

## Where your data goes outside the platform

The platform runs on infrastructure we rent. Each provider processes data on
our instructions and on our behalf; none owns it, and none may use it for their
own purposes. **Who they are at any moment is the list at
[/privacy/providers](/privacy/providers), which is part of this policy** — an
annex to it, not a leaflet beside it. What they do is here, because that is the
part that is a promise:

- **Supabase** — the database, sign-in, and uploaded files. Everything the
  platform stores is stored there, including the session record with your IP
  and User-Agent described above.
- **Vercel** — serves the site and the API; sees every request, including its
  IP address.
- **Datadog** — technical logs, error reports, and the session recordings
  described above.
- **Google (Gemini)** — **course content is sent to Google's Gemini models to be
  machine-translated** into the four languages the platform serves. What is sent
  is teacher-authored course material: titles, lesson text, quiz questions,
  announcements. **Student submissions are not sent, ever** — not for
  translation, not for anything else. We use the **paid** tier deliberately,
  and it is the difference that matters here: on the paid tier Google's own
  terms say it **does not use prompts or responses to improve its products**,
  logs them only for a limited period and only to catch abuse of its use
  policy, and does not have humans read them to make its models better. On the
  free tier all three of those are the other way round. If we ever moved off
  the paid tier this paragraph would stop being true, and we have written that
  down as a commitment to ourselves in the provider annex.
- **Google (sign-in)** — only if you use "Continue with Google", and only to
  authenticate you.
- **YouVersion** — the platform asks the YouVersion Bible API for the text of a
  verse, so that a passage quoted in a lesson is the real passage. It is asked
  for a reference; it is not told who asked.
- **Resend** — sends the platform's email. It holds the address the message went
  to, its subject and body, and whether it was accepted.

**When that list changes, we tell you.** Adding a provider, or swapping one for
another doing the same job, is published on the annex with the date it changed
and announced to you inside the platform, 60 days before it takes effect. You do
not have to agree to it — the promises in this policy have not moved — but you
are told in time to object, to ask us about it, or to close your account if the
answer does not satisfy you. Write to supportequip@gmail.com; we will answer.
What is *not* a mere change of supplier is a provider that would hold a category
of data no provider held before, or hold it for a new purpose. That is a change
to this policy itself, and it comes with a new version and a fresh request to
agree.

**Where all of this is, and what covers the journey.** Every provider above is
in the United States, and the platform is operated from there, so using it means
your data is processed in the United States. If you are in the European Economic
Area or the United Kingdom, that is a transfer out of your country, and each
provider's own data processing agreement says what protects it:

- **Supabase** — the European Standard Contractual Clauses, which its agreement
  treats as signed by our acceptance of it, with a UK addendum alongside.
- **Vercel** — the Standard Contractual Clauses, in the module that fits each
  role. They apply to Pro and Enterprise plans; ours is Pro.
- **Datadog** — the Standard Contractual Clauses and the UK International Data
  Transfer Addendum, both built into its agreement without a separate signature.
- **Resend** — certification under the EU–U.S. Data Privacy Framework and its UK
  extension, **and** the Standard Contractual Clauses on top.
- **Google** — **we have not confirmed this one and will not claim it.** The
  Gemini API is used through a Google AI Studio key, and we could not establish
  from Google's published terms which transfer mechanism covers that route.
  Until we can, treat Google as the gap in this list rather than assume it is
  like the other four. We would rather leave a hole here you can see than fill
  it with something we have not read.

**Why we hold what we hold.** For the law that asks this question directly: we
process your account and your coursework in order to provide the platform you
asked for and to perform what is agreed in these documents; we process technical
logs, error reports and session recordings on the basis of our legitimate
interest in a platform that works and can be repaired, weighed against the
honest description of it above; we process what a school gives us on that
school's instructions; and where we ever ask for your consent to something, we
ask for it separately and you can take it back. We do not sell anything, and
there is no processing here for advertising.

**Where your data comes from, when it is not from you.** Usually you type it in.
But a school administrator can enrol a student, which means the school gives us
that person's name and email address before that person has given us anything.
If that is how your account came to exist, the school is where it came from, and
you can ask us what we hold about you exactly as anybody else can.

## Who can see it inside the platform

- **Your course teacher** — your work, answers, marks and progress.
- **Your school's director or administrator** — the same, plus student lists and
  grade sheets.
- **Other students** — only your name and photograph, and only where that is
  part of the coursework itself (a review you left on a course, for instance).
- **The people who run the platform** — technically, anyone administering the
  database can see what is in it. We look when something is broken or when
  somebody reports a problem, not otherwise.
- **Anybody holding one of your certificate numbers.** A certificate is checked
  at `equipbible.com/verify/<number>`, without an account and without signing
  in, and the answer shows **the name it was issued to, the course title and the
  date**. That is what makes a certificate worth having; it also means those
  three things are visible to whoever you give the number to, and to whoever
  they give it to. Nothing else about you is shown, and a number that matches
  nothing shows nothing.
- **Nobody else.** We do not sell data, hand it to advertisers, or share it with
  third parties beyond the providers above.

We will hand over data if the law requires it — a court order, a lawful demand
from an authority — and we will tell you when we are allowed to.

## How long we keep it

| What | Where it lives | How long |
|---|---|---|
| Account and profile — name, email, photo, language | Supabase | While the account exists |
| Coursework — progress, quiz answers, submissions, marks, feedback | Supabase | While the account exists; deleted with it |
| Issued certificates and the grade sheets recording them | Supabase | **Kept after the account is deleted** — see below |
| Record of accepting a document like this one (version, fingerprint, language, time, IP) | Supabase | While the account exists — then **kept without you in it**, indefinitely (see below) |
| Declaration attached to a submission (statement, AI use, time, IP) | Supabase | While the submission exists |
| Audit record of actions — who did what, when (no IP) | Supabase | Kept; not deleted on a schedule today |
| Notifications shown to you in the platform | Supabase | Kept; not deleted on a schedule today |
| Uploaded course files | Supabase Storage | Until the teacher or the school removes them |
| Sign-in session record — IP and User-Agent | Supabase Auth | While the session is alive; ended when you sign out |
| Server and request logs, including IP | Datadog | **15 days** |
| Frontend session records and replays | Datadog | **30 days** (Datadog's retention for this data) |
| Sent email — address, subject, body, delivery result | Resend | Held by Resend under its own retention; we keep no copy in our database |
| Database backups | Supabase | A short rolling window set by our plan — a deletion becomes final when the backups holding it age out |

Where a row says "not deleted on a schedule today", that is the honest state:
the platform is young and no purge job runs yet. When one does, this table
changes and the change is notified rather than re-signed, because a shorter
retention is not a worse deal for you.

**What outlives your account.** Two things, and only two.

An issued certificate, and the grade sheet recording it, remain. A school
cannot retroactively un-witness what it has already witnessed, which is exactly
why those documents are frozen as a snapshot at the moment they are issued.

The record that you accepted a document like this one also remains, **with you
taken out of it**. At the moment your account is deleted, the account
identifier on that record is replaced by a one-way fingerprint of it and the IP
address is erased. What is left is which document, which version, in which
language, and when — and a fingerprint that cannot be turned back into your
name, your email address or your account. That is kept indefinitely, because a
consent record that vanishes with the account cannot answer the one question it
is kept to answer.

Everything else goes.

## What you can do

- **See and change your data** — in your profile, for what the profile holds.
- **Get a copy of everything held about you** — write to supportequip@gmail.com
  and we will put it together and send it. There is no self-service export
  button yet.
- **Delete your account and your coursework** — write to
  supportequip@gmail.com with the subject line **Delete my account**. There is
  no delete button in the profile and no self-service route: we do it by hand,
  and **within 30 days** of your asking. We will confirm when it is done and
  tell you what remained. What remains is the three things named above and
  nothing else: certificates already issued, the grade sheets recording them,
  and the record that you accepted these documents with you taken out of it.
- **Correct something that is wrong** — tell us and we will fix it.
- **Object to the session recording** — we cannot switch it off for one account
  today. If that is not acceptable to you, deleting the account is the honest
  remedy, and we will not make it difficult.
- **Withdraw consent** — which means deleting the account: using the platform
  without agreeing to this document is not technically possible.

We answer these within 30 days.

## Age

You can register yourself from **16**. Between **13 and 16** an account can only
be opened by a school administrator, and in that case the consent of whoever is
responsible for the student is the school's responsibility — they know the
family and we do not. That obligation is written into the
[School Agreement](/school-agreement) rather than assumed.

**Under 13, no account, by any route.** Not by signing up, and not by a school
administrator creating one. If we find an account belongs to a child under 13 we
close it and delete its data, and we will tell the school. If you believe a
child under 13 has an account here, write to supportequip@gmail.com and we will
deal with it.

## Email the platform sends

Three kinds, and no others:

- **Account mail** — confirming your address, resetting your password, an
  invitation somebody sent you. It cannot be turned off; without it an account
  cannot be used.
- **Course mail and notifications** — things you would be worse off not knowing:
  a session about to start, a certificate decided, work returned, a deadline
  moved, an announcement from your course. Each kind can be turned off in your
  profile, and every such message carries an unsubscribe link.
- **Nothing else.** No newsletters, no product announcements, no marketing, and
  no selling or renting your address to anybody.

## Things that may come later

Named here so that adding them is a notice rather than another signing round —
and each of them, when it arrives, will be described here in full before it
touches anybody's data:

- **Paid courses.** If a school ever charges for a course, a payment provider
  will handle the payment. **We will never hold your card number**; the provider
  will, and it will be named in the provider list with what it holds. Today
  there are no payments on the platform and we store no payment details.
- **Video hosted elsewhere.** A lesson may embed a video from a third-party
  service (YouTube today, by link). Playing it is a visit to that service, under
  that service's own terms, and it will see your request.
- **Fewer things, sooner.** Retention windows can only get shorter this way; a
  longer one is a material change.

## Changes to this policy

**A material change requires your agreement.** You will be asked to accept the
new version before you can carry on. A change is material if it does any of
these:

- adds a category of data we collect, or a new purpose for data we already hold;
- widens who can see your data, inside the platform or outside it;
- adds a provider that holds a category of data no provider held before, or
  holds it for a new purpose;
- lengthens how long something is kept;
- takes away one of the rights listed under **What you can do**.

**Anything else is notified, not re-signed.** Swapping one provider for another
doing the same job, shortening a retention window, adding a new right,
correcting a mistake, or saying the same thing more clearly — these are
published, you are told about them inside the platform, and they **take effect
60 days later**. You do not have to accept them; you may accept them sooner if
you want the new version to apply to you straight away, and if you would rather
not be bound by one you have those 60 days to ask us about it or to close your
account. The provider annex changes on the same terms and for the same reason: a
change of supplier moves no promise, and making it a fresh signing round would
train people to click through a consent screen without reading it, which is the
opposite of what consent is for.

Each version is stored with the date it took effect and a fingerprint of its
text, and the record of what you accepted names that version and that
fingerprint. Old versions are never rewritten.

## Languages

This document is published in English, Russian, German and Ukrainian. The
translations are provided so that everyone can read what they are agreeing to,
and we intend them to say the same thing. **If they differ, the English version
governs** — except where the law of the country you live in says otherwise.

## Law

The platform is operated from the United States (Indiana), and the law of that
state applies to this document. If you live somewhere whose data-protection law
gives you rights that cannot be signed away, this document does not sign them
away.

## Contact

**supportequip@gmail.com**

# Voice Guide

How Equip talks, in all four languages. Short on purpose — `DESIGN.md` is how
it looks, this is how it sounds. Rules marked **(tested)** are enforced by
`frontend/src/i18n/__tests__/russianStyle.test.ts`; the rest are for review.

## Who is speaking

**A teacher who respects you.** Not a coach, not a mascot, not a salesman.
Warm and plain; says what happened and what you can do next; never makes you
feel behind. The subject is Scripture, so the tone is quiet — the platform
does not get excited on its own behalf.

Reference points from the 2026-09-30 platform study: Headspace («a streak is
support, not a verdict»), Khan Academy («empowering, not condescending»).
Anti-references: Duolingo's guilt-tripping owl, the countdown timers of paid
language schools.

## Rules

1. **Formal address, everywhere.** ru «вы», uk «ви», de «Sie». A screen on «ты»
   reads as a different product. **(tested, ru)**
2. **No shame, no threat.** Never «вы потеряете серию», «вы нас подвели», «Бог
   ждёт вас». A missed day is met with «рады, что вы вернулись», not with a zero.
3. **Say the thing, then the next step.** «Работа проверена. Прочитать отзыв».
   Not «Отлично! 🎉 Ваша работа успешно проверена!»
4. **No exclamation runs, no emoji** in interface text or email. (`DESIGN.md`
   already bans emoji; this covers the words.)
5. **No game jargon.** No «XP», «уровень», «прокачать», «стрик». Say «дни с
   Писанием», «пройдено», «серия дней» only where there is one.
6. **The native word where the language has one.** ru «срок», not «дедлайн»;
   «главная», not «дашборд»; «живое занятие», not «прямая сессия». **(tested,
   ru)** «Аккаунт» and «онлайн» are fine — they are the words Russian uses now.
7. **Sentences about the work, not the gender of the person.** Russian and
   Ukrainian verbs carry gender in the past tense. Prefer «Ваша работа
   проверена» to «Преподаватель проверил(а)».
8. **Sacred words follow each language's own rules.** Capitalise «Бог», «Святой
   Дух», «Писание» in ru/uk; «Gott», «Heiliger Geist», «Schrift» in de. Never a
   joke about Scripture.
9. **Typography is part of the voice.** «Ёлочки» in ru/uk, „Anführungszeichen“
   in de, “curly” in en; an em dash with spaces in ru/uk; a comma before «чтобы»
   **(tested, ru)**. The lesson renderer keeps «Ин 3:16» and short prepositions
   on one line (`lib/typography.ts`).

## Words

| Say | Not | Why |
| --- | --- | --- |
| срок, срок сдачи | дедлайн | Russian has the word |
| главная | дашборд | ditto |
| живое занятие | прямая сессия, вебинар | it is a lesson, not a broadcast |
| пройдено | выполнено, зачтено (outside grades) | the reader completed a lesson, not a task |
| прочитать отзыв | посмотреть фидбек | ditto |
| урок | глава (in the student's view) | a student takes lessons; «глава» is the editor's word |
| Lektion, Frist | Deadline, Session | the German interface is formal |

## Email

The same voice, shorter. Subject says what happened («Работа «…» проверена»).
The sender is a person when there is one («Olena Koval via Equip»). One
button. One line at the bottom saying why the reader got it.

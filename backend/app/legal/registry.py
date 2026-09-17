"""Which documents exist, at which version, for whom, and what they say.

The registry is the whole point of this module. Before it, three facts lived in
three different heads: which documents a person has to sign, which version is
current, and whether a particular edit was big enough to ask everybody again.
The last of those is the expensive one — a project that cannot tell a typo from
a new obligation either re-signs the world over a comma, or quietly rewrites
what people agreed to. Both happened here.

So each revision carries ``consent``: ``True`` means "this version needs a
fresh acceptance", ``False`` means "this version is published and announced,
and nobody signs again". That is a property of the data, checked by tests, and
not a judgement made at the moment somebody is impatient to deploy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).parent / "documents"

#: The locales every document must exist in. A document missing one of these is
#: a broken deployment, not a fallback to English — a policy somebody cannot
#: read is not a policy they can accept.
#:
#: This was ``("ru", "en")`` until 2026-09-17, while the interface served four
#: languages: a German or Ukrainian reader was handed the English text with a
#: line apologising for it. Four now, translated by hand rather than through
#: the course translation pipeline, because a binding document is not content.
LOCALES = ("en", "ru", "de", "uk")

#: The language the documents are governed in, and the one served to a reader
#: whose language is not among ``LOCALES``. Named in every document's own
#: "Languages" section: where the translations differ, this one decides.
GOVERNING_LOCALE = "en"

#: Roles as the ``profiles.role`` column spells them. Imported from the model
#: would be a cycle; the four-way enum mirror in AGENTS.md covers the drift,
#: and ``tests/test_legal_registry.py`` pins these against ``UserRole``.
STUDENT = "student"
TEACHER = "teacher"
DIRECTOR = "director"
ADMIN = "admin"

#: Everybody with an account, whatever they are here to do.
EVERYONE = frozenset({STUDENT, TEACHER, DIRECTOR, ADMIN})

#: The people who can put material in front of other people, see other
#: people's work, and decide what a mark says. Directors teach too — the role
#: is "runs a school", not "does not enter a classroom".
TEACHING = frozenset({TEACHER, DIRECTOR, ADMIN})


@dataclass(frozen=True)
class Revision:
    """One published version of one document.

    ``consent`` is the field this registry exists for. A version that changes
    what somebody is agreeing to sets it ``True`` and brings everybody back to
    the gate. A version that fixes a typo, shortens a retention window, adds a
    right, or says the same thing more plainly sets it ``False``: it is
    published, the reader is told, and nobody signs anything. Each document
    defines "material" in its own text, so this flag is an editorial decision
    with a written rule behind it rather than a mood.
    """

    version: str
    effective: date
    consent: bool


@dataclass(frozen=True)
class DocumentSpec:
    """One document: who must sign it, and every version it has ever had."""

    slug: str
    #: Roles that have to have accepted it. Empty means nobody signs this one —
    #: it is a page the policies point at, read and never agreed to.
    required_for: frozenset[str]
    #: Oldest first. Never edited, only appended to: an acceptance row names a
    #: version, and a version whose meaning can be rewritten records nothing.
    revisions: tuple[Revision, ...]

    @property
    def current(self) -> Revision:
        return self.revisions[-1]

    @property
    def signable(self) -> bool:
        return bool(self.required_for)

    def index_of(self, version: str) -> int | None:
        for i, revision in enumerate(self.revisions):
            if revision.version == version:
                return i
        return None

    @property
    def consent_index(self) -> int:
        """Where the most recent version that needs signing sits.

        Everything published after it is notice-only, so somebody who accepted
        at or after this point is up to date even though a newer version
        exists. This is the single line that makes "a small edit does not need
        a signature" true of the data.
        """
        return max(i for i, revision in enumerate(self.revisions) if revision.consent)


#: Every document the platform publishes, signed or not.
#:
#: Version history is kept in full. ``privacy`` and ``terms`` were rewritten on
#: 2026-09-17 — the privacy policy because it described less than the platform
#: actually did (session recording, request logs, machine translation), the
#: terms because the platform had no licence, no warranty from the uploader and
#: no indemnity. Both are ``consent=True``: everyone signs once more, and the
#: mechanism above exists so that this is the last time a correction costs a
#: signing round.
LEGAL_REGISTRY: tuple[DocumentSpec, ...] = (
    DocumentSpec(
        slug="privacy",
        required_for=EVERYONE,
        revisions=(
            Revision("1.0", date(2026, 8, 13), consent=True),
            Revision("1.1", date(2026, 9, 12), consent=True),
            Revision("2.0", date(2026, 9, 17), consent=True),
        ),
    ),
    DocumentSpec(
        slug="terms",
        required_for=EVERYONE,
        revisions=(
            Revision("1.0", date(2026, 8, 13), consent=True),
            Revision("1.1", date(2026, 9, 12), consent=True),
            Revision("2.0", date(2026, 9, 17), consent=True),
        ),
    ),
    DocumentSpec(
        slug="teacher-terms",
        required_for=TEACHING,
        revisions=(Revision("1.0", date(2026, 9, 17), consent=True),),
    ),
    DocumentSpec(
        slug="providers",
        required_for=frozenset(),
        revisions=(
            Revision("2026-09-12", date(2026, 9, 12), consent=False),
            Revision("2026-09-17", date(2026, 9, 17), consent=False),
        ),
    ),
)

_BY_SLUG: dict[str, DocumentSpec] = {spec.slug: spec for spec in LEGAL_REGISTRY}

#: slug -> current version, for the documents that are actually signed. Derived
#: rather than hand-maintained, so it cannot drift from the registry above.
LEGAL_DOCUMENTS: dict[str, str] = {spec.slug: spec.current.version for spec in LEGAL_REGISTRY if spec.signable}

#: The pages the policies point at, which are read and never signed.
#:
#: The distinction is the whole point. A consent record answers "which text did
#: this person agree to", and every version bump asks everyone to answer it
#: again. Housekeeping — which supplier holds the database this quarter — does
#: not change a single promise, and making it a version bump would train people
#: to click through a consent screen without reading it.
REFERENCE_DOCUMENTS: dict[str, str] = {spec.slug: spec.current.version for spec in LEGAL_REGISTRY if not spec.signable}

#: (slug, version, locale) -> sha256 of the file as served.
#:
#: Production holds two different ``content_sha256`` values for each document
#: at version 1.0: the texts were edited after people had accepted them, and
#: the version was not moved. The acceptance rows are still true — each names
#: the hash of the text it was given — but the version alone no longer says
#: which text that was, which is the one question a consent record is kept to
#: answer.
#:
#: This table makes that edit impossible to make quietly. The test in
#: ``tests/test_a_changed_text_is_a_new_version.py`` hashes every document and
#: compares it with the entry here; a changed file fails CI until the author
#: either reverts the text or adds a revision to the registry and pins the new
#: version's fingerprints below. Old versions stay listed — they are the record
#: of what the rows in ``legal_acceptances`` refer to.
LEGAL_DOCUMENT_FINGERPRINTS: dict[tuple[str, str, str], str] = {
    ("privacy", "1.0", "en"): "32b29998946040ebf9651eba8df40f1fd141f5c5d3dbbd68ed897fb893265c57",
    ("privacy", "1.0", "ru"): "bcd8dd40c868c5881d46d891dc4520a2268579470ebdf7c992cf9c46f927de1a",
    ("terms", "1.0", "en"): "a4edd70619d288b248d9385e024b78b0e00813471e7dee424e9ed8a5e2e11654",
    ("terms", "1.0", "ru"): "c7f4997fd3c81eb9a4872628993a31d35828db50fa00e9e204f936e7b8b045ac",
    ("terms", "1.1", "en"): "9e557f01a0b4188067b9c62bf02d647e5035dfe594fa506fed770dd136069c30",
    ("terms", "1.1", "ru"): "1f6c209ec108bbb483907f4cf44a182e82c1521ae89b2440ac8b618c9af7e9b1",
    ("privacy", "1.1", "en"): "fbc305b6b7fc7cb98f0281a64f2d5724c7c0037d58656b677e43eafbeb867ae6",
    ("privacy", "1.1", "ru"): "5a1ab9ddd4647562347069733af3cfa521b8d3f0a916922b48307bbac825f37a",
    # 2026-09-17: everything rewritten, and everything translated into the two
    # languages these documents never existed in. Sixteen files, four of them
    # a document nobody had been asked to sign before.
    ("privacy", "2.0", "en"): "540a380618141c8e55c7fc6069e0e8d4732d3330e1141dc466cded6acb1d58af",
    ("privacy", "2.0", "ru"): "83e6597ddf60a7c3de46750b003d7b2d3e833ea461841d8b93ce3dfbc3ce110b",
    ("privacy", "2.0", "de"): "8da5b91192a69a048694b6b7177173d9c05f8687580a1e602f58da78cc7514b5",
    ("privacy", "2.0", "uk"): "6bdbc333ca5a360df8ca768676aa6bcdfb8c1509bc315d3932e47dbc8a1f3f1a",
    ("terms", "2.0", "en"): "f39c83564e045d89fb685520e6242ce5dc6379b650910eafda5215c9826daabe",
    ("terms", "2.0", "ru"): "795772d825725e102d5707c888e2489078fa5caedab063cd3cb9dd9420c8d4a3",
    ("terms", "2.0", "de"): "c49cb17a83ca0cdb0039ccc3a399dad5da9c8ee89c1a9eb3b003711de42e8bfb",
    ("terms", "2.0", "uk"): "e08d42fe79f7b07aa5ff3bb760a0c9c40a63944cb63ebb3a22bb5a3f2c7477c2",
    ("teacher-terms", "1.0", "en"): "b37421241999bc1f176209181e7c238467688d8c6ecf48803ed0559d407cb2f8",
    ("teacher-terms", "1.0", "ru"): "3cdbcfa92500c975e9cd99119441094b88f16907c227adf98168dcf540482180",
    ("teacher-terms", "1.0", "de"): "432abd2fbca7bd352ccdddec7f4fba09dbcc60c87c8448ec40a1ce8a2b543370",
    ("teacher-terms", "1.0", "uk"): "ff545b36416669c6f5cd30af354316dac4fa448e36c0e3f8de3ab8e1a8406718",
    # The provider list is fingerprinted too, although nobody signs it: the
    # page is the answer to "who held my data in September", and a page that
    # can be rewritten under that question answers it badly.
    ("providers", "2026-09-17", "en"): "d80ed2f326eaab5ec8aad30698363904001700fedad0a908c4f6016be4048e5a",
    ("providers", "2026-09-17", "ru"): "b7bb545d03f610dfe94f93b88dff8bd10226fc2dfdd749e4f8c6e13118291bc1",
    ("providers", "2026-09-17", "de"): "efd92c11e8bfc51b50e9fbeafadab97b130ae86ea4337554b47b2d9c84001a8d",
    ("providers", "2026-09-17", "uk"): "2959f11fa30e4a2f79dd320706061d1b34475fb17c13195cafb2ff410ad3b095",
}


@dataclass(frozen=True)
class LegalDocument:
    """One document, in one language, at one version."""

    slug: str
    version: str
    locale: str
    body: str

    @property
    def sha256(self) -> str:
        """The fingerprint stored against an acceptance.

        Computed from the bytes served, so a change of a single word in a
        published document is visible in the record afterwards — which is how
        "you agreed to this" stays a checkable claim rather than an assertion.
        """
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


#: Every file that may ever be read here, keyed by what may ask for it.
_DOCUMENT_PATHS: dict[tuple[str, str], Path] = {
    (spec.slug, locale): DOCUMENTS_DIR / f"{spec.slug}.{locale}.md" for spec in LEGAL_REGISTRY for locale in LOCALES
}


def document_spec(slug: str) -> DocumentSpec:
    """The registry entry for a slug, or ``KeyError``."""
    try:
        return _BY_SLUG[slug]
    except KeyError as exc:
        raise KeyError(f"unknown legal document: {slug}") from exc


def required_slugs(role: str | None = None) -> tuple[str, ...]:
    """What a person in this role must have accepted to use the platform.

    ``None`` means "every document anybody signs" — what the public documents
    route answers with, since it has no user to ask about.
    """
    return tuple(spec.slug for spec in LEGAL_REGISTRY if spec.signable and (role is None or role in spec.required_for))


def outstanding_for(role: str, accepted: set[tuple[str, str]]) -> tuple[DocumentSpec, ...]:
    """Documents this person has to accept before carrying on.

    ``accepted`` is every ``(slug, version)`` already on record for them. A
    person is up to date on a document when they have accepted **any** version
    at or after its most recent ``consent=True`` revision — which is what lets a
    notice-only version ship without a gate. An unknown version (a row written
    by a registry older than this code) counts as older than everything, which
    is the safe direction: at worst somebody is asked once more.
    """
    owed = []
    for slug in required_slugs(role):
        spec = document_spec(slug)
        mine = [spec.index_of(version) for s, version in accepted if s == slug]
        best = max((i for i in mine if i is not None), default=-1)
        if best < spec.consent_index:
            owed.append(spec)
    return tuple(owed)


def notices_for(role: str, accepted: set[tuple[str, str]]) -> tuple[DocumentSpec, ...]:
    """Documents that changed since this person signed, without needing a signature.

    They are told, once, what moved and where to read it. They are not asked to
    agree again, because nothing they agreed to has changed — that is the whole
    promise of ``consent=False``, and the reason a typo does not cost a
    hundred people a click.
    """
    changed = []
    for slug in required_slugs(role):
        spec = document_spec(slug)
        mine = [spec.index_of(version) for s, version in accepted if s == slug]
        best = max((i for i in mine if i is not None), default=-1)
        if spec.consent_index <= best < len(spec.revisions) - 1:
            changed.append(spec)
    return tuple(changed)


@cache
def document_for(slug: str, locale: str) -> LegalDocument:
    """Load one document, or raise if it is missing.

    The returned document carries the locale it *is*, which is not always the
    locale that was asked for — a language these documents do not exist in gets
    the governing one. Every caller reads ``doc.locale`` rather than the
    request's, so the acceptance record says which text the person actually saw
    and the page can tell them which language they are reading.

    Cached because these are immutable files read on nearly every sign-in, and
    uncached because the cache is per-process — a deploy replaces the process,
    which is the only moment the files can change.
    """
    spec = document_spec(slug)
    served = locale if locale in LOCALES else GOVERNING_LOCALE
    # Looked up, not built. The filename used to be interpolated from the
    # arguments behind an ``if locale not in LOCALES: raise``, and dropping
    # that check for the fallback dropped the only thing standing between a
    # request parameter and a path on disk. Selecting from a table built out
    # of constants means an unexpected value can miss, and cannot escape.
    path = _DOCUMENT_PATHS[spec.slug, served]
    if not path.is_file():
        # Deliberately fatal rather than falling back to another language: a
        # required document is missing from the build.
        raise FileNotFoundError(f"legal document missing from the build: {path.name}")
    return LegalDocument(
        slug=spec.slug,
        version=spec.current.version,
        locale=served,
        body=path.read_text(encoding="utf-8"),
    )

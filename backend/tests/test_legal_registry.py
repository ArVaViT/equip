"""The registry decides who signs what, and which edits cost a signature.

Three things used to be judgement calls made at the keyboard: whether a change
was big enough to ask everybody again, which documents a teacher owes that a
student does not, and whether the version somebody accepted is still current.
All three are now fields in ``app.legal.registry``, and these tests are what
makes them fields rather than intentions.

The last group is deliberately mutation-style: it edits a copy of the registry
and asserts the answers change. A test that passes against both a rule and its
opposite is not testing the rule.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date

from app.legal import (
    EVERYONE,
    LEGAL_DOCUMENTS,
    LEGAL_REGISTRY,
    LOCALES,
    TEACHING,
    DocumentSpec,
    Revision,
    document_for,
    document_spec,
    notices_for,
    outstanding_for,
    required_slugs,
)
from app.legal.registry import VERSION_HEADLINE, headline_version
from app.models.user import UserRole

# ── The shape of the registry itself ──────────────────────────────────


def test_every_role_named_in_the_registry_is_a_role_that_exists() -> None:
    # The four-way enum mirror in AGENTS.md, applied to a fifth place: a
    # document required for "instructor" would simply never be asked of
    # anybody, silently.
    real = {role.value for role in UserRole}
    for spec in LEGAL_REGISTRY:
        assert spec.required_for <= real, f"{spec.slug} requires an unknown role"
    assert real >= EVERYONE
    assert real >= TEACHING


def test_versions_are_unique_and_dated_forwards() -> None:
    for spec in LEGAL_REGISTRY:
        versions = [revision.version for revision in spec.revisions]
        assert len(versions) == len(set(versions)), f"{spec.slug} repeats a version"
        dates = [revision.effective for revision in spec.revisions]
        assert dates == sorted(dates), f"{spec.slug} has revisions out of order"


def test_a_document_anybody_signs_has_something_to_sign() -> None:
    for spec in LEGAL_REGISTRY:
        if spec.signable:
            assert any(revision.consent for revision in spec.revisions), (
                f"{spec.slug} must be accepted by somebody but no revision ever asked"
            )


def test_a_page_nobody_signs_never_asks_for_a_signature() -> None:
    # ``providers`` is the reason this distinction exists: swapping a supplier
    # must not oblige a hundred people to agree to anything again.
    for spec in LEGAL_REGISTRY:
        if not spec.signable:
            assert not any(revision.consent for revision in spec.revisions)
            assert spec.slug not in LEGAL_DOCUMENTS


def test_the_school_agreement_is_asked_of_a_director_and_nobody_else() -> None:
    # It is the one document accepted on somebody else's behalf: a director
    # signing it binds the organisation. A platform administrator is us, not a
    # school — there is no organisation for them to bind, so they are never
    # shown it, and neither is a teacher or a student.
    assert "school-agreement" in required_slugs("director")
    for role in ("student", "teacher", "admin"):
        assert "school-agreement" not in required_slugs(role), f"{role} is being asked to bind a school on its behalf"


def test_the_teacher_agreement_is_asked_of_teachers_and_not_of_students() -> None:
    assert "teacher-terms" in required_slugs("teacher")
    assert "teacher-terms" in required_slugs("director")
    assert "teacher-terms" not in required_slugs("student")
    # Everybody signs the other two, whatever they are here to do.
    for role in ("student", "teacher", "director", "admin"):
        assert {"privacy", "terms"} <= set(required_slugs(role))


# ── Four languages, or it is not a document ───────────────────────────


def test_every_document_exists_in_all_four_languages() -> None:
    # The interface serves four languages. Until 2026-09-17 these documents
    # existed in two, and a German reader was shown the English text with a
    # line apologising for it — which is a policy they were asked to accept
    # without being given it in their own language.
    assert set(LOCALES) == {"en", "ru", "de", "uk"}
    for spec in LEGAL_REGISTRY:
        for locale in LOCALES:
            doc = document_for(spec.slug, locale)
            assert doc.locale == locale
            assert doc.body.strip(), f"{spec.slug}.{locale} is empty"


def test_a_language_we_do_not_serve_gets_the_governing_text() -> None:
    doc = document_for("terms", "fr")
    assert doc.locale == "en"


def test_every_translation_says_which_version_governs() -> None:
    # Each document carries its own language clause. A translation that drops
    # it is a translation claiming equal force with the text it was made from.
    for spec in LEGAL_REGISTRY:
        if not spec.signable:
            continue
        for locale in LOCALES:
            body = document_for(spec.slug, locale).body
            assert "English" in body or "английск" in body or "Englisch" in body or "англійськ" in body, (
                f"{spec.slug}.{locale} does not say the English text governs"
            )


# ── What a person owes, and what they are merely told ─────────────────


def test_a_person_who_has_accepted_nothing_owes_everything_for_their_role() -> None:
    owed = {spec.slug for spec in outstanding_for("student", set())}
    assert owed == set(required_slugs("student"))
    assert "teacher-terms" not in owed

    owed_teacher = {spec.slug for spec in outstanding_for("teacher", set())}
    assert "teacher-terms" in owed_teacher


def test_accepting_the_current_version_clears_it() -> None:
    accepted = {(slug, version) for slug, version in LEGAL_DOCUMENTS.items()}
    assert outstanding_for("teacher", accepted) == ()
    assert notices_for("teacher", accepted) == ()


def test_an_old_version_of_a_rewritten_document_is_still_owed() -> None:
    # Everybody on the platform accepted privacy 1.0 or 1.1. Both were
    # superseded by a 2.0 that says materially different things, so both are
    # owed again — deliberately, and once.
    owed = {spec.slug for spec in outstanding_for("student", {("privacy", "1.1"), ("terms", "1.1")})}
    assert owed == {"privacy", "terms"}


def test_a_version_this_code_has_never_heard_of_counts_as_older() -> None:
    # A row written by a registry that has since been rewritten. Being asked
    # once more is the safe direction to be wrong in.
    owed = {spec.slug for spec in outstanding_for("student", {("privacy", "0.4")})}
    assert "privacy" in owed


# ── The mechanism itself: a small edit must not cost a signature ──────


def _registry_with(spec: DocumentSpec) -> tuple[DocumentSpec, ...]:
    return tuple(s if s.slug != spec.slug else spec for s in LEGAL_REGISTRY)


def _rebind(monkeypatch, registry: tuple[DocumentSpec, ...]) -> None:
    """Point the registry module's lookups at a doctored copy."""
    from app.legal import registry as module

    monkeypatch.setattr(module, "LEGAL_REGISTRY", registry)
    monkeypatch.setattr(module, "_BY_SLUG", {spec.slug: spec for spec in registry})


def test_a_notice_only_revision_is_announced_and_not_signed(monkeypatch) -> None:
    privacy = document_spec("privacy")
    patched = dataclasses.replace(
        privacy,
        revisions=(*privacy.revisions, Revision("2.1", date(2026, 10, 1), consent=False)),
    )
    _rebind(monkeypatch, _registry_with(patched))

    accepted = {("privacy", "2.0"), ("terms", "2.0")}
    assert outstanding_for("student", accepted) == ()
    assert [spec.slug for spec in notices_for("student", accepted)] == ["privacy"]


def test_the_same_revision_marked_material_does_cost_a_signature(monkeypatch) -> None:
    # The mutation. Identical registry, identical acceptance, one flag flipped:
    # if this test and the one above could both pass, ``consent`` would be
    # decoration.
    privacy = document_spec("privacy")
    patched = dataclasses.replace(
        privacy,
        revisions=(*privacy.revisions, Revision("2.1", date(2026, 10, 1), consent=True)),
    )
    _rebind(monkeypatch, _registry_with(patched))

    accepted = {("privacy", "2.0"), ("terms", "2.0")}
    assert [spec.slug for spec in outstanding_for("student", accepted)] == ["privacy"]
    assert notices_for("student", accepted) == ()


def test_dropping_a_role_from_a_document_stops_it_being_asked(monkeypatch) -> None:
    teacher_terms = document_spec("teacher-terms")
    patched = dataclasses.replace(teacher_terms, required_for=frozenset({"director"}))
    _rebind(monkeypatch, _registry_with(patched))

    assert "teacher-terms" not in required_slugs("teacher")
    assert "teacher-terms" in required_slugs("director")


# ── The translations are the same document, not a different one ───────


def _shape(body: str) -> dict[str, object]:
    """The structure of a Markdown document, ignoring every word in it.

    Not a style check. A translation that has one heading fewer than the
    English has dropped a section, and the section a legal document is most
    likely to lose in translation is a long one near the end — which here is
    the arbitration clause, the change procedure and the language clause.
    """
    lines = body.splitlines()
    return {
        "headings": [line.count("#") for line in lines if line.startswith("#")],
        "bullets": sum(1 for line in lines if line.startswith("- ")),
        "numbered": sum(1 for line in lines if re.match(r"^\d+\. ", line)),
        "table_rows": sum(1 for line in lines if line.startswith("|")),
        "bold": body.count("**"),
        # Sorted with duplicates kept: a translation that drops one of the two
        # links to the teacher agreement has dropped a cross-reference, and a
        # cross-reference is how these documents say who else is bound.
        "links": sorted(part.split(")")[0] for part in body.split("](")[1:]),
    }


def test_every_translation_has_the_same_shape_as_the_english() -> None:
    for spec in LEGAL_REGISTRY:
        english = _shape(document_for(spec.slug, "en").body)
        for locale in LOCALES:
            if locale == "en":
                continue
            other = _shape(document_for(spec.slug, locale).body)
            for key, value in english.items():
                assert other[key] == value, (
                    f"{spec.slug}.{locale}.md differs from the English in {key}: "
                    f"{other[key]!r} vs {value!r}. A translation with a different "
                    "shape has gained or lost something."
                )


def test_the_documents_keep_the_promises_the_product_makes_elsewhere() -> None:
    # Not stylistic assertions. Each of these is a claim the product makes in
    # code or a decision recorded elsewhere, and a document that contradicts it
    # is worse than no document.
    for locale in LOCALES:
        terms = document_for("terms", locale).body
        privacy = document_for("privacy", locale).body
        teacher = document_for("teacher-terms", locale).body
        school = document_for("school-agreement", locale).body

        # The address every notice goes to, in every document that names one.
        for body in (terms, privacy, teacher, school):
            assert "supportequip@gmail.com" in body

        # Two age floors, and both have to be in both places that enforce them:
        # 16 to sign up, 13 absolutely, whoever is doing the creating.
        for body in (terms, privacy, school):
            assert "13" in body
        assert "16" in terms
        assert "16" in privacy

        # What the privacy policy exists to be honest about.
        assert "Datadog" in privacy
        assert "Gemini" in privacy
        assert "15" in privacy  # the request-log retention window
        # The verification link shows a name to anybody holding the number, and
        # both documents that could hide that say it instead.
        assert "verify" in privacy
        assert "verify" in terms

        # The dispute route as it now is: write first, wait 30 days, Indiana.
        # And as it is not — an arbitration clause that came out deliberately
        # must not survive in one language because a translation was patched
        # rather than rewritten.
        assert "30" in terms
        assert "Indiana" in terms or "Индиан" in terms or "Індіан" in terms
        assert "Arbitration opt-out" not in terms

        # The most expensive single risk, and the platform's own undertaking
        # about it.
        assert "1202" in terms

        # The three occupied regions, named because US law requires it.
        assert "WCAG 2.1" in terms

        # The teacher agreement's whole reason to exist.
        assert "PDF" in teacher


def test_no_document_still_promises_arbitration() -> None:
    """It was taken out on purpose, in every language, in every file.

    A cross-reference is the easy place for a removed clause to survive: the
    teacher agreement incorporated "the arbitration clause and the class-action
    waiver — and your right to opt out of them" from the Terms of Use for
    several hours after the Terms had stopped having any. Three translators
    caught it independently, which is a good sign about them and a bad sign
    about relying on a reader to notice.
    """
    allowed = {"terms"}  # the Terms say, once, that there is none
    for spec in LEGAL_REGISTRY:
        for locale in LOCALES:
            body = document_for(spec.slug, locale).body.lower()
            for word in ("arbitrat", "арбитраж", "арбітраж", "schieds"):
                if word in body:
                    assert spec.slug in allowed, (
                        f"{spec.slug}.{locale}.md still mentions arbitration ({word!r}). "
                        "The clause was removed; a cross-reference to it is a promise "
                        "the Terms of Use expressly deny."
                    )


# ── A document has to say which version it is ─────────────────────────


def test_every_document_says_its_own_version_and_says_the_right_one() -> None:
    """The headline on the page and the version in the registry must agree.

    They drifted apart once and nobody noticed: ``terms.en.md`` said "Version
    1.0" for a month while the registry served 1.1, and nine people accepted
    1.1. Every one of those rows names a version that was nowhere on the page
    the person read — which turns "you agreed to version 1.1" into a claim we
    could not show anybody.

    A missing or malformed headline fails here too. A legal document that does
    not state its own version cannot be the evidence for an acceptance that
    names one.
    """
    for spec in LEGAL_REGISTRY:
        if not spec.signable:
            # The provider annex is dated rather than versioned; its own test
            # is that the date in the file matches the registry, below.
            continue
        for locale in LOCALES:
            doc = document_for(spec.slug, locale)
            claimed = headline_version(doc.body, locale)
            assert claimed is not None, (
                f"{spec.slug}.{locale}.md has no version headline the parser recognises. "
                f"Expected a second line matching {VERSION_HEADLINE[locale]!r}."
            )
            assert claimed == spec.current.version, (
                f"{spec.slug}.{locale}.md says it is version {claimed!r}, "
                f"but the registry serves {spec.current.version!r}. An acceptance would "
                "name a version the reader never saw."
            )


def test_the_provider_annex_is_dated_the_day_the_registry_says() -> None:
    # Its "version" is the date it last changed, so the two have to match in
    # the one place a reader can check: the top of the page.
    spec = document_spec("providers")
    day, month, year = spec.current.effective.day, spec.current.effective.month, spec.current.effective.year
    english = document_for("providers", "en").body
    assert str(year) in english.splitlines()[2]
    assert str(day) in english.splitlines()[2]
    assert month == 9

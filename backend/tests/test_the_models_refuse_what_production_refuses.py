"""The models refuse what production refuses, and no more.

Every test in this suite runs on a database built from ``Base.metadata``.
Production runs on what ``supabase/schema.sql`` records. When the two
disagree about a rule, the suite proves the code against a database nobody
deploys — and the disagreement is invisible, because each side is internally
consistent.

It happened. ``assignment_submissions`` carried ``UNIQUE (assignment_id,
student_id)`` in production and not in the model; ``submit_assignment`` writes
a new row on every resubmission, the tests for resubmission were green, and in
production the second hand-in would have been a 409. ``student_grades`` carried
``UNIQUE (student_id, course_id)`` beside the cohort-aware unique the model
declares, which would have refused a student's grade in their second cohort.
Both tables were empty, so nobody had met either.

This compares the two on the things a row or a query can feel — PRIMARY KEY
and UNIQUE column sets, nullability, which column lists are indexed — and not
on names. A difference either gets fixed or is listed below with the fact that
makes it right; an entry whose difference is gone fails too, so the list
cannot outlive its reasons.
"""

from __future__ import annotations

import re

import pytest

from app.core.database import Base
from tests._schema_shape import SCHEMA_SQL, TableShape, read_metadata, read_schema_sql

#: Differences that are right, each with the fact that makes it right.
KNOWN_DIFFERENCES: dict[str, str] = {
    "profiles: unique (email) only in the models": (
        "profiles.email is a copy: handle_new_user writes it from auth.users and "
        "profiles_protect_immutable_fields refuses any direct change. The uniqueness lives on "
        "the original, auth.users_email_partial_key UNIQUE (email) WHERE is_sso_user = false, "
        "and no SAML provider is configured, so that predicate covers every account. The "
        "test database has no auth schema, so the model states the rule on the copy."
    ),
}


def _render_unique(key: tuple[frozenset[str], bool]) -> str:
    columns, nnd = key
    return f"({', '.join(sorted(columns))})" + (" NULLS NOT DISTINCT" if nnd else "")


def _differences(production: dict[str, TableShape], models: dict[str, TableShape]) -> set[str]:
    found: set[str] = set()
    for table in sorted(set(production) - set(models)):
        found.add(f"{table}: table only in production")
    for table in sorted(set(models) - set(production)):
        found.add(f"{table}: table only in the models")
    for table in sorted(set(production) & set(models)):
        prod, model = production[table], models[table]
        if prod.primary_key != model.primary_key:
            found.add(
                f"{table}: primary key ({', '.join(prod.primary_key)}) in production, ({', '.join(model.primary_key)}) in the models"
            )
        for key in prod.unique_keys() - model.unique_keys():
            found.add(f"{table}: unique {_render_unique(key)} only in production")
        for key in model.unique_keys() - prod.unique_keys():
            found.add(f"{table}: unique {_render_unique(key)} only in the models")
        for column in sorted(set(prod.columns) - set(model.columns)):
            found.add(f"{table}.{column}: column only in production")
        for column in sorted(set(model.columns) - set(prod.columns)):
            found.add(f"{table}.{column}: column only in the models")
        for column in sorted(set(prod.columns) & set(model.columns)):
            if prod.columns[column] != model.columns[column]:
                side = "production" if not prod.columns[column] else "the models"
                found.add(f"{table}.{column}: NOT NULL only in {side}")
        # One direction only. An index production has and the models lack
        # changes no query result, only its speed on a database the tests do
        # not measure. An index the models have and production lacks is a
        # promise nobody keeps: whoever reads the model believes the lookup is
        # indexed.
        for name, index in sorted(model.indexes.items()):
            if index.key not in prod.index_keys():
                found.add(f"{table}: index {name} ({', '.join(index.key)}) only in the models")
    for side, shapes in (("production", production), ("the models", models)):
        for table, shape in sorted(shapes.items()):
            for name in shape.indexes_repeating_a_unique_key():
                found.add(f"{table}: index {name} in {side} repeats a unique key")
    return found


@pytest.fixture(scope="module")
def differences() -> set[str]:
    return _differences(read_schema_sql(), read_metadata(Base.metadata))


def test_the_dump_is_read_whole():
    """The reader must see every table and index the dump holds.

    A reader that silently skipped a line it did not understand would make
    every comparison below vacuous for that line.
    """
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    shapes = read_schema_sql()
    assert len(shapes) == len(re.findall(r"^CREATE TABLE ", text, flags=re.MULTILINE))
    declared = len(re.findall(r"^CREATE (UNIQUE )?INDEX ", text, flags=re.MULTILINE)) + len(
        re.findall(r"^\s+ADD CONSTRAINT \w+ (PRIMARY KEY|UNIQUE) ", text, flags=re.MULTILINE)
    )
    assert sum(len(s.indexes) for s in shapes.values()) == declared
    assert all(s.primary_key for s in shapes.values())


def test_the_models_and_production_agree(differences: set[str]):
    unexplained = sorted(differences - set(KNOWN_DIFFERENCES))
    assert not unexplained, "The models and supabase/schema.sql disagree:\n" + "\n".join(unexplained)


def test_every_listed_difference_still_exists(differences: set[str]):
    stale = sorted(set(KNOWN_DIFFERENCES) - differences)
    assert not stale, "Listed as known but no longer different — remove from KNOWN_DIFFERENCES:\n" + "\n".join(stale)

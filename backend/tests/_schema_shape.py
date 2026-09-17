"""The shape of a schema, reduced to what a query or a write can feel.

Two readers produce the same record: one reads ``supabase/schema.sql`` (the
``pg_dump`` of production), the other reads ``Base.metadata`` (what the tests
build their database from). Names are left out on purpose. Production and the
models name the same rule differently all over the place, and a name never
refused a row. What refuses a row is the set of columns a UNIQUE covers and
whether a column takes NULL; what makes a query fast is the column list an
index is keyed on.

The ``pg_dump`` reader reads ``pg_dump`` output, not SQL in general. It leans
on the dump's fixed layout — one column per line inside ``CREATE TABLE``, one
``ADD CONSTRAINT`` line after ``ALTER TABLE ONLY``, one ``CREATE INDEX`` per
line — and raises on any line of those kinds it cannot place, so a layout it
does not understand fails the test instead of being skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Column, Index, MetaData, PrimaryKeyConstraint, UniqueConstraint

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"


@dataclass(frozen=True, order=True)
class IndexShape:
    """An index as a write or a lookup meets it.

    ``key`` keeps order — ``(a, b)`` answers ``WHERE a = ?`` and ``(b, a)``
    does not — with expressions as normalized text. Sort direction is dropped:
    it does not change which lookups the index serves.

    ``nulls_not_distinct`` is kept, because it changes which rows a UNIQUE
    refuses. ``COALESCE(col, <constant>)`` in a unique key is read as ``col``
    with NULLs not distinct: the two spellings refuse exactly the same rows,
    and production uses both.
    """

    key: tuple[str, ...]
    unique: bool
    partial: bool
    nulls_not_distinct: bool = False


@dataclass
class TableShape:
    columns: dict[str, bool] = field(default_factory=dict)  # column -> nullable
    primary_key: tuple[str, ...] = ()
    #: Every index-backed object by its name on that side.
    indexes: dict[str, IndexShape] = field(default_factory=dict)

    def unique_keys(self) -> set[tuple[frozenset[str], bool]]:
        """Column sets that may not repeat, from constraints and unique indexes alike.

        A partial unique index is left out: it forbids a repeat only inside its
        predicate, which is a different rule from the one a full UNIQUE states.
        """
        return {(frozenset(i.key), i.nulls_not_distinct) for i in self.indexes.values() if i.unique and not i.partial}

    def index_keys(self) -> set[tuple[str, ...]]:
        return {i.key for i in self.indexes.values()}

    def indexes_repeating_a_unique_key(self) -> list[str]:
        """Plain indexes keyed exactly like a PRIMARY KEY or UNIQUE on the same table.

        The unique one already answers every lookup the plain one could, so the
        plain one only costs writes.
        """
        unique = {i.key for i in self.indexes.values() if i.unique and not i.partial}
        return sorted(n for n, i in self.indexes.items() if not i.unique and not i.partial and i.key in unique)


_COALESCE = re.compile(r"^coalesce\(([a-z_][a-z0-9_]*),'[^']*'\)$")


def _normalize_element(expr: str) -> tuple[str, bool]:
    """One spelling for one key element, whichever side wrote it.

    Returns the element and whether it stands for a column whose NULLs are not
    distinct (the ``COALESCE`` idiom).
    """
    expr = expr.strip()
    expr = re.sub(r"\s+(ASC|DESC)\b", "", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\s+NULLS\s+(FIRST|LAST)\b", "", expr, flags=re.IGNORECASE)
    # pg_dump spells out the casts a model's text() leaves implicit.
    expr = re.sub(r"::[a-z ]+(\(\d+\))?", "", expr, flags=re.IGNORECASE)
    expr = re.sub(r"[\s\"]", "", expr).lower()
    while expr.startswith("(") and expr.endswith(")") and _matching_paren(expr, 0) == len(expr) - 1:
        expr = expr[1:-1]
    if m := _COALESCE.match(expr):
        return m.group(1), True
    return expr, False


def _key(elements: list[str]) -> tuple[tuple[str, ...], bool]:
    normalized = [_normalize_element(e) for e in elements]
    return tuple(n for n, _ in normalized), any(nnd for _, nnd in normalized)


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_quote = False
    for ch in text:
        if ch == "'":
            in_quote = not in_quote
        elif not in_quote and ch == "(":
            depth += 1
        elif not in_quote and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not in_quote:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p for p in (p.strip() for p in parts) if p]


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    in_quote = False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "'":
            in_quote = not in_quote
        elif not in_quote and ch == "(":
            depth += 1
        elif not in_quote and ch == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"unbalanced parentheses in: {text}")


_CREATE_TABLE = re.compile(r"^CREATE TABLE public\.(\w+) \($")
_COLUMN_LINE = re.compile(r"^    (\"?[a-z_][a-z0-9_]*\"?) ")
_ALTER_ONLY = re.compile(r"^ALTER TABLE ONLY public\.(\w+)$")
_ADD_KEY = re.compile(r"^\s+ADD CONSTRAINT (\w+) (PRIMARY KEY|UNIQUE)( NULLS NOT DISTINCT)? \((.+)\);$")
_ADD_OTHER = re.compile(r"^\s+ADD CONSTRAINT \w+ (FOREIGN KEY|CHECK|EXCLUDE) ")
_CREATE_INDEX = re.compile(r"^CREATE (UNIQUE )?INDEX (\w+) ON public\.(\w+) USING \w+ (\(.*)$")


def read_schema_sql(path: Path = SCHEMA_SQL) -> dict[str, TableShape]:
    tables: dict[str, TableShape] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if m := _CREATE_TABLE.match(line):
            shape = tables.setdefault(m.group(1), TableShape())
            i += 1
            # Columns come first, then table CONSTRAINTs, some of which run over
            # several lines. The body ends at ")" or ") WITH (...)".
            in_columns = True
            while not lines[i].startswith(")"):
                if lines[i].startswith("    CONSTRAINT "):
                    in_columns = False
                if in_columns:
                    col = _COLUMN_LINE.match(lines[i])
                    if col is None:
                        raise ValueError(f"schema.sql: cannot place column line: {lines[i]}")
                    shape.columns[col.group(1).strip('"')] = not lines[i].rstrip(",").endswith(" NOT NULL")
                i += 1
        elif (m := _ALTER_ONLY.match(line)) and i + 1 < len(lines) and " ADD CONSTRAINT " in lines[i + 1]:
            nxt = lines[i + 1]
            if k := _ADD_KEY.match(nxt):
                name, kind, nnd, cols = k.groups()
                key, coalesced = _key(_split_top_level(cols))
                shape = tables.setdefault(m.group(1), TableShape())
                shape.indexes[name] = IndexShape(
                    key=key, unique=True, partial=False, nulls_not_distinct=bool(nnd) or coalesced
                )
                if kind == "PRIMARY KEY":
                    shape.primary_key = key
            elif not _ADD_OTHER.match(nxt):
                raise ValueError(f"schema.sql: cannot place constraint line: {nxt}")
            i += 1
        elif m := _CREATE_INDEX.match(line):
            unique, name, table, rest = m.groups()
            close = _matching_paren(rest, 0)
            key, coalesced = _key(_split_top_level(rest[1:close]))
            tail = rest[close + 1 :]
            tables.setdefault(table, TableShape()).indexes[name] = IndexShape(
                key=key,
                unique=bool(unique),
                partial=" WHERE " in tail,
                nulls_not_distinct=coalesced or "NULLS NOT DISTINCT" in tail,
            )
        elif line.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX", "CREATE TABLE")):
            raise ValueError(f"schema.sql: cannot place line: {line}")
        i += 1
    return tables


def read_metadata(metadata: MetaData) -> dict[str, TableShape]:
    tables: dict[str, TableShape] = {}
    for table in metadata.tables.values():
        shape = TableShape(columns={c.name: bool(c.nullable) for c in table.columns})
        for constraint in table.constraints:
            if not isinstance(constraint, PrimaryKeyConstraint | UniqueConstraint):
                continue
            key = tuple(c.name for c in constraint.columns)
            # ``unique=True`` on a column and an unnamed PRIMARY KEY carry no name
            # until DDL time; give them one here so they do not overwrite each other.
            kind = "pkey" if isinstance(constraint, PrimaryKeyConstraint) else "key"
            name = constraint.name if isinstance(constraint.name, str) else f"{table.name}_{'_'.join(key)}_{kind}"
            shape.indexes[name] = IndexShape(
                key=key,
                unique=True,
                partial=False,
                nulls_not_distinct=bool(constraint.dialect_options["postgresql"].get("nulls_not_distinct")),
            )
            if isinstance(constraint, PrimaryKeyConstraint):
                shape.primary_key = key
        for index in table.indexes:
            shape.indexes[str(index.name)] = _metadata_index(index)
        tables[table.name] = shape
    return tables


def _metadata_index(index: Index) -> IndexShape:
    # A non-column element prints qualified ("assignment_submissions.submitted_at DESC").
    qualifier = f"{index.table.name}." if index.table is not None else ""
    elements = [e.name if isinstance(e, Column) else str(e).replace(qualifier, "") for e in index.expressions]
    key, coalesced = _key(elements)
    postgresql = index.dialect_options["postgresql"]
    return IndexShape(
        key=key,
        unique=bool(index.unique),
        partial=postgresql.get("where") is not None or index.dialect_options["sqlite"].get("where") is not None,
        nulls_not_distinct=coalesced or bool(postgresql.get("nulls_not_distinct")),
    )

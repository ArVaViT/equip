"""Cut a lesson block into pieces the model can carry without dropping any.

Why this exists
---------------

A chapter block is TipTap HTML, and a long one is a lot to ask for in a
single breath. The block that forced this module carries 85 tags —
``div``, ``em``, ``h2``, ``img``, ``p``, ``strong`` — and asked to
translate the whole document in one call the model sometimes came back
with markup that does not match: all seven ``<em>`` gone (the tags
marking the very terms the lesson is about), or six ``<strong>``
invented, or a chapter-and-verse reference missing. Structural
validation caught it every time — ``markup_mismatch``,
``verse_reference_lost`` — so the row was parked and never served,
which is right.

Two of those three verdicts have since been narrowed (2026-08-20): a
lost ``<em>`` is now ``emphasis_lost`` and a lost pointer is now
non-blocking, so neither withholds the lesson on its own. That changes
nothing about this module. What is compared here is the piece against
its own source, and the piece that came back wrong is asked again on
its own merits — the correcting pass below is driven by that
comparison, not by whether the whole document would have been parked.

But a parked row is a hole. The reader asks for the lesson in their
language and gets nothing where a block should be. Two blocks sat in
exactly that state, and they were the last remaining cause of parked
rows in production.

Retrying does not help. Sampling is at temperature 0, so the identical
question gets the identical answer, and the correcting pass that quotes
the defect back only sometimes recovers a document this large — the
model has to hold 85 tags in place while rewriting every sentence
between them, and it drops one.

So the document is cut at boundaries that are safe, each piece is
translated on its own, and the pieces are put back together. A
paragraph is a far smaller surface to mangle, and a lost ``<em>`` in
one paragraph is a defect the correcting pass can actually fix, because
it is being asked to fix a paragraph rather than a lesson.

What "safe" means here
----------------------

A cut may only fall *between* two top-level nodes — never inside an
element, never inside an attribute value, never between a ``<ul>`` and
its ``<li>`` children. The scanner below therefore walks the document
tracking quote state and tag depth, and a piece boundary is only ever
placed at a position where the depth is zero and the next node is a
block element.

A ``<ul>`` is one top-level node, so its list items (and any list
nested inside them) travel together by construction. A
``<div class="callout">`` is one top-level node for the same reason:
the wrapper and everything it wraps go in one piece. Nothing descends
into a wrapper — a piece must be a balanced fragment, and handing the
model half of a ``<div>`` would be inventing the failure this module
exists to remove.

Anything the scanner cannot account for — a stray closing tag, an
element left open at the end — means we do not understand the document
well enough to cut it, and it goes to the model whole, exactly as it
did before. Not splitting is always a legal answer.

What is judged per piece, and what is judged whole
--------------------------------------------------

Only one thing is checked per piece: whether the markup came back. That
is a property of a fragment, it is what a fragment gets wrong, and it is
what a fragment can be asked to fix.

Everything else is a property of the document and stays there:

* **Length.** A ratio computed on one paragraph is noise — German runs
  long here and short there, and rejecting a paragraph for a ratio that
  only makes sense across a lesson would park rows that are perfectly
  fine.
* **Verse references, scripture markers, placeholders, language,
  untranslated runs.** A reference can legitimately be absent from four
  pieces out of five. The count that matters is the document's.
* **Review.** The second model reads the finished translation against
  the finished source. Reading each piece separately would cost five
  reviews for one opinion and would ask the reviewer to judge register
  from a paragraph.
* **Glossary.** Two halves: the *hint* is per piece and is better for
  it — ``build_user_prompt`` filters the table by the terms the text in
  front of it actually uses, so a piece carries exactly its own lines
  rather than the lesson's. The *check* is on the whole, where "the
  translation does not contain this term" is a true statement.

So the pieces are a transport detail. ``executor._ask`` sees one source
and one translation, and validates them exactly as it did before this
module existed.
"""

from __future__ import annotations

import logging
from typing import Final

from app.services.translation.validation import tag_names

logger = logging.getLogger(__name__)

# Elements with no closing tag. Getting this list wrong would make the
# depth counter drift and the balance check reject documents that are
# perfectly fine — so it is the HTML spec's list, not a guess.
_VOID_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

# Where a cut is allowed to fall: the block-level elements TipTap emits
# at the top of a document. ``p``, ``h2``, ``h3``, ``li``, ``blockquote``
# and ``div`` are the ones the failing block is made of; the rest are
# here so that a document built out of lists, figures or a table is cut
# at the same kind of seam rather than not at all.
#
# ``li`` is in the set and ``ul`` is too, and those do not fight: a
# ``<li>`` is only ever a *top-level* node when the document is a bare
# run of list items with no list around them. Where there is a ``<ul>``,
# the ``<ul>`` is the top-level node and the items are inside it.
_BLOCK_BOUNDARY_TAGS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "ul",
        "ol",
        "li",
        "div",
        "section",
        "article",
        "figure",
        "pre",
        "table",
        "hr",
    }
)

# Above this many tags, a document is cut up; at or below it, it goes in
# one call exactly as it always has.
#
# Where 40 comes from: the block that fails carries 85 tags, and every
# other block in the corpus translates in one call — those two parked
# rows were the only structural failures left. So the boundary between
# "fine" and "too much to hold" sits somewhere below 85 and above
# typical, and typical is far below both. 40 is half of the document we
# know breaks: it leaves the overwhelming majority of blocks on the
# single-call path they already succeed on, and it does not wait for a
# document to be as bad as the worst one we have seen before helping it.
#
# Erring low is cheap and erring high is not. A document split when it
# did not need to be costs a few more calls at a fraction of a cent; a
# document not split when it needed to be costs the reader the whole
# lesson.
_SPLIT_ABOVE_TAGS: Final[int] = 40

# What each piece aims for. Not a hard cap — a single top-level node is
# never cut open, so a node bigger than this travels alone.
#
# 20 rather than 5: the model is good at this, and the cost of a piece
# is a call. At 20 the 85-tag block becomes five pieces of roughly a
# section each, and the seven ``<em>`` that vanished together are spread
# across pieces where one or two at a time is an easy ask. Smaller
# pieces would also start costing the translator the context that makes
# terminology consistent across a paragraph.
_TARGET_TAGS_PER_PIECE: Final[int] = 20


def _scan_tag(html: str, start: int) -> tuple[int, str, str] | None:
    """Read the tag beginning at ``html[start]``, which must be ``<``.

    Returns ``(end_index, tag_name, kind)`` where ``kind`` is one of
    ``open`` / ``close`` / ``void`` / ``other`` (comment, doctype,
    processing instruction), or ``None`` when the ``<`` does not begin a
    tag at all and is simply a character in the prose.

    The attribute walk tracks quote state, which is the whole point:
    ``alt="a > b"`` contains a ``>`` that ends nothing, and a scanner
    that stopped at it would report a boundary in the middle of an
    attribute value.
    """
    length = len(html)
    if start + 1 >= length:
        return None
    nxt = html[start + 1]

    if html.startswith("<!--", start):
        close = html.find("-->", start + 4)
        return (length if close == -1 else close + 3, "", "other")
    if nxt in "!?":
        close = html.find(">", start + 1)
        return (length if close == -1 else close + 1, "", "other")

    cursor = start + 1
    closing = nxt == "/"
    if closing:
        cursor += 1
    name_start = cursor
    while cursor < length and (html[cursor].isalnum() or html[cursor] in "-_:"):
        cursor += 1
    name = html[name_start:cursor].lower()
    if not name or not name[0].isalpha():
        # "5 < 7" and friends: a lone angle bracket in the prose.
        return None

    quote = ""
    while cursor < length:
        char = html[cursor]
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == ">":
            if closing:
                return (cursor + 1, name, "close")
            self_closing = html[cursor - 1] == "/"
            if self_closing or name in _VOID_ELEMENTS:
                return (cursor + 1, name, "void")
            return (cursor + 1, name, "open")
        cursor += 1
    # A tag with no ``>`` at all: it runs to the end of the document, so
    # everything after it travels with it and no cut can land inside it.
    # Reported as "other" — it opens nothing, which means an element
    # still on the stack stays open and the balance check refuses the
    # document outright.
    return (length, name, "other")


def _top_level_nodes(html: str) -> list[tuple[int, int, str]] | None:
    """The document's top-level nodes as ``(start, end, tag_name)`` spans.

    Text nodes carry ``""`` as their name. The spans are contiguous and
    cover the whole string, so any partition along them reassembles
    exactly.

    ``None`` means the document is not balanced the way this scanner
    understands balance — a closing tag with nothing open, a closing tag
    that does not match what is open, an element still open at the end.
    The caller must then treat the document as one piece: cutting a
    document we have misread is precisely how a fragment ends up
    unbalanced.
    """
    nodes: list[tuple[int, int, str]] = []
    stack: list[str] = []
    node_start = 0
    element_start = 0
    element_name = ""
    pos = 0
    length = len(html)

    while pos < length:
        lt = html.find("<", pos)
        if lt == -1:
            break
        parsed = _scan_tag(html, lt)
        if parsed is None:
            pos = lt + 1
            continue
        end, name, kind = parsed

        if kind == "open":
            if not stack:
                if lt > node_start:
                    nodes.append((node_start, lt, ""))
                element_start = lt
                element_name = name
            stack.append(name)
        elif kind in ("void", "other"):
            if not stack:
                if lt > node_start:
                    nodes.append((node_start, lt, ""))
                nodes.append((lt, end, name))
                node_start = end
        elif kind == "close":
            if not stack or stack[-1] != name:
                return None
            stack.pop()
            if not stack:
                nodes.append((element_start, end, element_name))
                node_start = end
        pos = end

    if stack:
        return None
    if node_start < length:
        nodes.append((node_start, length, ""))
    return nodes


def split_html_for_translation(html: str) -> list[str]:
    """Cut ``html`` into pieces to translate separately, or return it whole.

    The contract the caller relies on: ``"".join(result) == html``,
    always. A one-element list is the normal answer and means "ask for
    this in one call" — short documents, documents the scanner could not
    read, documents with a single top-level node.
    """
    if len(tag_names(html)) <= _SPLIT_ABOVE_TAGS:
        return [html]

    nodes = _top_level_nodes(html)
    if nodes is None or len(nodes) < 2:
        return [html]

    pieces: list[str] = []
    piece_start = 0
    piece_tags = 0
    for start, end, name in nodes:
        node_tags = len(tag_names(html[start:end]))
        may_cut_here = name in _BLOCK_BOUNDARY_TAGS
        if piece_tags and may_cut_here and piece_tags + node_tags > _TARGET_TAGS_PER_PIECE:
            pieces.append(html[piece_start:start])
            piece_start = start
            piece_tags = 0
        piece_tags += node_tags
    pieces.append(html[piece_start:])

    # Checked here rather than trusted, because everything downstream is
    # built on it: the translated pieces are concatenated in this order
    # and nothing else puts the document back together. A partition that
    # lost or duplicated a character would ship a corrupted lesson, so a
    # partition that does not reassemble is not used.
    if "".join(pieces) != html:
        logger.error("html_split_not_lossless pieces=%d chars=%d", len(pieces), len(html))
        return [html]
    return pieces


def markup_correction_note(source_piece: str, translated_piece: str) -> str | None:
    """What to tell the model about the markup it changed, or ``None``.

    The comparison is the same one ``validation._check_tags`` makes —
    the multiset of tag names, imported from there rather than
    reimplemented, so "the structure survived" means one thing in this
    codebase and not two. If these two ever disagreed, a piece would
    pass here and the reassembled document would still be parked.
    """
    expected = tag_names(source_piece)
    got = tag_names(translated_piece)
    if expected == got:
        return None
    missing = sorted(set(expected) - set(got))
    added = sorted(set(got) - set(expected))
    parts = []
    if missing:
        parts.append(f"dropped {', '.join(f'<{name}>' for name in missing)}")
    if added:
        parts.append(f"added {', '.join(f'<{name}>' for name in added)}")
    if not parts:
        parts.append("returned a different number of the same tags")
    return (
        f"You changed the markup: {'; '.join(parts)}. "
        f"The source has {len(expected)} tags and your answer has {len(got)}. "
        "Return exactly the same tags, in the same order and the same "
        "nesting, and translate only the text between them."
    )


__all__ = [
    "markup_correction_note",
    "split_html_for_translation",
]

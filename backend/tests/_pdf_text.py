"""Read the visible text back out of a generated PDF.

The PDF export's failure mode is a valid document with something
missing from it, so its tests have to assert on what the pages say —
not on the ``%PDF-`` magic, which stays correct while a whole section
of the course goes absent.

reportlab writes page content as Flate-compressed, ASCII85-armoured
streams whose visible words are the operands of the ``Tj`` operator.
No PDF library is installed and one export is not worth adding a
dependency for, so the two encodings are undone here.
"""

from __future__ import annotations

import base64
import contextlib
import re
import zlib

_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
_SHOWN = re.compile(rb"\(((?:\\.|[^()\\])*)\)\s*Tj")


def pdf_lines(pdf: bytes) -> list[str]:
    """Every run of visible text in the document, in the order it prints."""
    out: list[str] = []
    for match in _STREAM.finditer(pdf):
        raw = match.group(1).strip()
        # A stream reportlab left unarmoured stays as it is and simply
        # yields no ``Tj`` operands.
        with contextlib.suppress(ValueError, zlib.error):
            raw = zlib.decompress(base64.a85decode(raw, adobe=True))
        for shown in _SHOWN.findall(raw):
            out.append(shown.replace(rb"\(", b"(").replace(rb"\)", b")").decode("latin-1"))
    return out


def printed_order(pdf: bytes, titles: list[str]) -> list[str]:
    """The given titles in the order the document shows them.

    Each survives twice — once in the contents, once as a body heading —
    so a caller asserting ``expected * 2`` has pinned both lists at once.
    """
    wanted = set(titles)
    return [line for line in pdf_lines(pdf) if line in wanted]

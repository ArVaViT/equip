"""Which generation of translation rules is currently in force.

Raise this number whenever a change makes new translations better than
old ones — a glossary entry, a prompt rule, a new correcting pass, a
verse that now resolves to canon instead of to the model.

What happens then needs no further action from anyone: every stored
machine translation made by a lower version is treated exactly like a
missing one, so the reconciler sweep finds it, the queue picks it up,
and the catalogue re-translates itself in the background. Improving
quality is editing a prompt and raising a constant.

What must NOT raise it: a refactor, a rename, a bug fix that changes no
output. Each bump is a full re-translation of everything, and the point
of the number is that it means something.

History
-------
0   Everything made before this was tracked.
1   The glossary (a term is the same term everywhere), per-language
    calque notes, the correcting pass that quotes a rejected wording
    back at temperature 0, answer options included in verse
    substitution, and matching an author's quotation against every
    edition held rather than the first one that answers.
"""

from __future__ import annotations

from typing import Final

TRANSLATOR_VERSION: Final[int] = 1

__all__ = ["TRANSLATOR_VERSION"]
